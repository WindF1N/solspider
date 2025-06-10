#!/usr/bin/env python3
"""
Анализ развития токенов на DEX биржах после обнаружения твитов с контрактами
"""

import pandas as pd
import aiohttp
import asyncio
from datetime import datetime, timedelta
import logging
import time
from dotenv import load_dotenv
from database import get_db_manager, Token
from logger_config import setup_logging

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class DexAnalyzer:
    """Анализатор развития токенов на DEX"""
    
    def __init__(self):
        self.session = None
        self.dexscreener_base = "https://api.dexscreener.com/latest"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_token_data(self, mint_address):
        """Получает данные токена с DexScreener"""
        try:
            url = f"{self.dexscreener_base}/dex/tokens/{mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    logger.warning(f"⚠️ Rate limit для {mint_address}, ждем...")
                    await asyncio.sleep(2)
                    return await self.get_token_data(mint_address)
                else:
                    logger.warning(f"⚠️ Ошибка API для {mint_address}: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных для {mint_address}: {e}")
            return None
    
    async def analyze_token_performance(self, token):
        """Анализирует производительность токена"""
        try:
            logger.info(f"🔍 Анализируем токен {token.symbol} ({token.mint})")
            
            # Получаем данные с DexScreener
            dex_data = await self.get_token_data(token.mint)
            
            if not dex_data or not dex_data.get('pairs'):
                logger.warning(f"⚠️ Нет данных DEX для {token.symbol}")
                return None
            
            # Берем самую ликвидную пару
            pairs = dex_data['pairs']
            main_pair = max(pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0))
            
            if not main_pair:
                return None
            
            # Время обнаружения контракта
            detection_time = token.updated_at if token.updated_at else token.created_at
            token_age_hours = (datetime.utcnow() - token.created_at).total_seconds() / 3600
            
            # Текущие данные
            current_price = float(main_pair.get('priceUsd', 0) or 0)
            current_mcap = float(main_pair.get('marketCap', 0) or 0)
            liquidity_usd = float(main_pair.get('liquidity', {}).get('usd', 0) or 0)
            volume_24h = float(main_pair.get('volume', {}).get('h24', 0) or 0)
            
            # Изменения цены
            price_change_5m = float(main_pair.get('priceChange', {}).get('m5', 0) or 0)
            price_change_1h = float(main_pair.get('priceChange', {}).get('h1', 0) or 0)
            price_change_6h = float(main_pair.get('priceChange', {}).get('h6', 0) or 0)
            price_change_24h = float(main_pair.get('priceChange', {}).get('h24', 0) or 0)
            
            # Анализ входных точек и потенциальной прибыли
            entry_amounts = [5, 10, 20, 50, 100, 1000]  # USD
            performance_analysis = {}
            
            for amount in entry_amounts:
                if current_price > 0:
                    tokens_bought = amount / current_price
                    
                    # Рассчитываем потенциальную прибыль при различных сценариях
                    scenarios = {
                        '2x': tokens_bought * current_price * 2,
                        '5x': tokens_bought * current_price * 5,
                        '10x': tokens_bought * current_price * 10,
                        '50x': tokens_bought * current_price * 50,
                        '100x': tokens_bought * current_price * 100
                    }
                    
                    performance_analysis[f'${amount}'] = {
                        'tokens_bought': tokens_bought,
                        'scenarios': scenarios
                    }
            
            # Определяем статус токена
            status = "Неактивен"
            if volume_24h > 10000:
                status = "Очень активен"
            elif volume_24h > 1000:
                status = "Активен"
            elif volume_24h > 100:
                status = "Умеренно активен"
            elif volume_24h > 10:
                status = "Низкая активность"
            
            # Оценка ликвидности
            liquidity_status = "Низкая"
            if liquidity_usd > 100000:
                liquidity_status = "Очень высокая"
            elif liquidity_usd > 50000:
                liquidity_status = "Высокая"
            elif liquidity_usd > 10000:
                liquidity_status = "Средняя"
            elif liquidity_usd > 1000:
                liquidity_status = "Низкая"
            else:
                liquidity_status = "Очень низкая"
            
            result = {
                'token': token,
                'dex_data': main_pair,
                'analysis': {
                    'current_price': current_price,
                    'current_mcap': current_mcap,
                    'liquidity_usd': liquidity_usd,
                    'volume_24h': volume_24h,
                    'price_changes': {
                        '5m': price_change_5m,
                        '1h': price_change_1h,
                        '6h': price_change_6h,
                        '24h': price_change_24h
                    },
                    'status': status,
                    'liquidity_status': liquidity_status,
                    'token_age_hours': token_age_hours,
                    'detection_time': detection_time,
                    'performance_analysis': performance_analysis
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа токена {token.symbol}: {e}")
            return None

async def analyze_contract_tokens():
    """Анализирует все токены с найденными контрактами"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        logger.info("🔍 Загружаем токены с найденными контрактами...")
        
        # Получаем токены с контрактами, отсортированные по количеству твитов
        tokens = session.query(Token).filter(
            Token.twitter_contract_tweets > 0,
            Token.mint.isnot(None),
            Token.symbol.isnot(None)
        ).order_by(Token.twitter_contract_tweets.desc()).limit(50).all()  # Ограничиваем для тестирования
        
        logger.info(f"📊 Найдено {len(tokens)} токенов для анализа")
        
        results = []
        
        async with DexAnalyzer() as analyzer:
            for i, token in enumerate(tokens, 1):
                logger.info(f"📈 Анализ {i}/{len(tokens)}: {token.symbol}")
                
                result = await analyzer.analyze_token_performance(token)
                if result:
                    results.append(result)
                
                # Небольшая пауза чтобы не перегружать API
                await asyncio.sleep(0.5)
        
        session.close()
        return results
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}")
        return []

def create_performance_excel(results):
    """Создает Excel файл с анализом производительности"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"dex_performance_analysis_{timestamp}.xlsx"
        
        # Основная таблица с результатами
        main_data = []
        
        # Детальная таблица входных точек
        entry_analysis_data = []
        
        for result in results:
            token = result['token']
            analysis = result['analysis']
            
            # Основные данные
            main_row = {
                'Символ': token.symbol,
                'Название': token.name or 'N/A',
                'Адрес контракта': token.mint,
                'Твитов с контрактом': token.twitter_contract_tweets,
                'Время создания': token.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Время обнаружения': analysis['detection_time'].strftime('%Y-%m-%d %H:%M:%S'),
                'Возраст (часы)': f"{analysis['token_age_hours']:.1f}",
                
                # DEX данные
                'Текущая цена ($)': f"{analysis['current_price']:.10f}" if analysis['current_price'] else 'N/A',
                'Market Cap ($)': f"{analysis['current_mcap']:,.0f}" if analysis['current_mcap'] else 'N/A',
                'Ликвидность ($)': f"{analysis['liquidity_usd']:,.0f}" if analysis['liquidity_usd'] else 'N/A',
                'Объем 24h ($)': f"{analysis['volume_24h']:,.0f}" if analysis['volume_24h'] else 'N/A',
                
                # Изменения цены
                'Изменение 5м (%)': f"{analysis['price_changes']['5m']:.2f}",
                'Изменение 1ч (%)': f"{analysis['price_changes']['1h']:.2f}",
                'Изменение 6ч (%)': f"{analysis['price_changes']['6h']:.2f}",
                'Изменение 24ч (%)': f"{analysis['price_changes']['24h']:.2f}",
                
                # Статусы
                'Статус активности': analysis['status'],
                'Статус ликвидности': analysis['liquidity_status'],
                
                # Ссылки
                'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                'Pump.fun': f"https://pump.fun/{token.mint}"
            }
            main_data.append(main_row)
            
            # Анализ входных точек
            for entry_amount, data in analysis['performance_analysis'].items():
                for scenario, profit in data['scenarios'].items():
                    entry_row = {
                        'Символ': token.symbol,
                        'Вход ($)': entry_amount,
                        'Куплено токенов': f"{data['tokens_bought']:.6f}",
                        'Сценарий': scenario,
                        'Потенциальная прибыль ($)': f"{profit:,.2f}",
                        'ROI (%)': f"{((profit / float(entry_amount.replace('$', ''))) - 1) * 100:.0f}",
                        'Текущая цена': f"{analysis['current_price']:.10f}",
                        'Объем 24h': f"{analysis['volume_24h']:,.0f}",
                        'Ликвидность': f"{analysis['liquidity_usd']:,.0f}"
                    }
                    entry_analysis_data.append(entry_row)
        
        # Создаем DataFrame'ы
        main_df = pd.DataFrame(main_data)
        entry_df = pd.DataFrame(entry_analysis_data)
        
        # Сохраняем в Excel
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Основной анализ
            main_df.to_excel(writer, sheet_name='Общий анализ', index=False)
            
            # Анализ входных точек
            entry_df.to_excel(writer, sheet_name='Анализ входов', index=False)
            
            # Статистика по категориям
            stats_data = []
            
            # Статистика по активности
            activity_stats = main_df['Статус активности'].value_counts()
            for status, count in activity_stats.items():
                stats_data.append({
                    'Категория': 'Активность',
                    'Значение': status,
                    'Количество': count,
                    'Процент': f"{(count/len(main_df)*100):.1f}%"
                })
            
            # Статистика по ликвидности
            liquidity_stats = main_df['Статус ликвидности'].value_counts()
            for status, count in liquidity_stats.items():
                stats_data.append({
                    'Категория': 'Ликвидность',
                    'Значение': status,
                    'Количество': count,
                    'Процент': f"{(count/len(main_df)*100):.1f}%"
                })
            
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_excel(writer, sheet_name='Статистика', index=False)
            
            # Автоподгонка ширины колонок для всех листов
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
                
                # Замораживаем заголовки
                worksheet.freeze_panes = 'A2'
        
        logger.info(f"✅ Анализ DEX производительности сохранен в {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания Excel: {e}")
        return None

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск анализа производительности токенов на DEX")
    
    # Анализируем токены
    results = await analyze_contract_tokens()
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    logger.info(f"📊 Проанализировано {len(results)} токенов")
    
    # Создаем Excel отчет
    filename = create_performance_excel(results)
    
    if filename:
        logger.info(f"📈 ИТОГОВЫЙ АНАЛИЗ:")
        logger.info(f"  • Файл: {filename}")
        logger.info(f"  • Токенов проанализировано: {len(results)}")
        
        # Статистика
        active_count = sum(1 for r in results if r['analysis']['volume_24h'] > 1000)
        high_liquidity_count = sum(1 for r in results if r['analysis']['liquidity_usd'] > 10000)
        
        logger.info(f"  • Активных токенов (>$1k объем): {active_count}")
        logger.info(f"  • С высокой ликвидностью (>$10k): {high_liquidity_count}")
        
        # Лучшие по росту за 24ч
        top_gainers = sorted(results, key=lambda x: x['analysis']['price_changes']['24h'], reverse=True)[:5]
        logger.info(f"📈 ТОП-5 по росту за 24ч:")
        for i, r in enumerate(top_gainers, 1):
            change = r['analysis']['price_changes']['24h']
            logger.info(f"  {i}. {r['token'].symbol}: {change:+.2f}%")
    
    logger.info("✅ Анализ завершен!")

if __name__ == "__main__":
    asyncio.run(main()) 