#!/usr/bin/env python3
"""
Продвинутый анализ корреляции между твитами с контрактами и движением цены токенов
"""

import pandas as pd
import aiohttp
import asyncio
from datetime import datetime, timedelta
import logging
import numpy as np
from dotenv import load_dotenv
from database import get_db_manager, Token
from logger_config import setup_logging

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

class AdvancedMarketAnalyzer:
    """Продвинутый анализатор рынка"""
    
    def __init__(self):
        self.session = None
        self.dexscreener_base = "https://api.dexscreener.com/latest"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_token_full_data(self, mint_address):
        """Получает полные данные токена включая исторические"""
        try:
            url = f"{self.dexscreener_base}/dex/tokens/{mint_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    await asyncio.sleep(2)
                    return await self.get_token_full_data(mint_address)
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных для {mint_address}: {e}")
            return None
    
    def calculate_roi_scenarios(self, current_price, entry_amounts):
        """Рассчитывает ROI сценарии для разных входов"""
        scenarios = {}
        
        for amount in entry_amounts:
            if current_price > 0:
                tokens_bought = amount / current_price
                scenarios[amount] = {
                    'tokens': tokens_bought,
                    'roi_2x': (tokens_bought * current_price * 2) - amount,
                    'roi_5x': (tokens_bought * current_price * 5) - amount,
                    'roi_10x': (tokens_bought * current_price * 10) - amount,
                    'roi_50x': (tokens_bought * current_price * 50) - amount,
                    'roi_100x': (tokens_bought * current_price * 100) - amount,
                    'percentage_2x': 100,  # 2x = 100% прибыль
                    'percentage_5x': 400,  # 5x = 400% прибыль
                    'percentage_10x': 900, # 10x = 900% прибыль
                    'percentage_50x': 4900, # 50x = 4900% прибыль
                    'percentage_100x': 9900 # 100x = 9900% прибыль
                }
        
        return scenarios
    
    def analyze_tweet_impact(self, token):
        """Анализирует влияние твитов на токен"""
        
        # Время с момента создания до обнаружения контракта
        time_to_discovery = None
        if token.updated_at and token.created_at:
            time_to_discovery = (token.updated_at - token.created_at).total_seconds() / 3600
        
        # Возраст токена на момент обнаружения
        token_age_at_discovery = time_to_discovery if time_to_discovery else 0
        
        # Категоризация по скорости обнаружения
        discovery_category = "Неизвестно"
        if time_to_discovery is not None:
            if time_to_discovery <= 1:
                discovery_category = "Мгновенное (≤1ч)"
            elif time_to_discovery <= 6:
                discovery_category = "Быстрое (1-6ч)"
            elif time_to_discovery <= 24:
                discovery_category = "Среднее (6-24ч)"
            else:
                discovery_category = "Медленное (>24ч)"
        
        # Оценка активности твитов
        tweet_activity = "Низкая"
        if token.twitter_contract_tweets >= 10:
            tweet_activity = "Очень высокая"
        elif token.twitter_contract_tweets >= 5:
            tweet_activity = "Высокая"
        elif token.twitter_contract_tweets >= 2:
            tweet_activity = "Средняя"
        
        return {
            'time_to_discovery': time_to_discovery,
            'token_age_at_discovery': token_age_at_discovery,
            'discovery_category': discovery_category,
            'tweet_activity': tweet_activity,
            'total_contract_tweets': token.twitter_contract_tweets,
            'total_symbol_tweets': token.twitter_symbol_tweets or 0
        }

async def analyze_market_impact():
    """Анализирует влияние твитов на рынок"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        logger.info("🔍 Загружаем токены для продвинутого анализа...")
        
        # Получаем токены с контрактами
        tokens = session.query(Token).filter(
            Token.twitter_contract_tweets > 0,
            Token.mint.isnot(None),
            Token.symbol.isnot(None),
            Token.updated_at.isnot(None)  # Только токены с известным временем обнаружения
        ).order_by(Token.twitter_contract_tweets.desc()).limit(100).all()
        
        logger.info(f"📊 Найдено {len(tokens)} токенов для анализа")
        
        results = []
        entry_amounts = [5, 10, 20, 50, 100, 1000]
        
        async with AdvancedMarketAnalyzer() as analyzer:
            for i, token in enumerate(tokens, 1):
                logger.info(f"📈 Анализ {i}/{len(tokens)}: {token.symbol}")
                
                # Анализ влияния твитов
                tweet_impact = analyzer.analyze_tweet_impact(token)
                
                # Получаем данные с DEX
                dex_data = await analyzer.get_token_full_data(token.mint)
                
                if dex_data and dex_data.get('pairs'):
                    # Берем самую ликвидную пару
                    pairs = dex_data['pairs']
                    main_pair = max(pairs, key=lambda x: float(x.get('liquidity', {}).get('usd', 0) or 0))
                    
                    if main_pair:
                        current_price = float(main_pair.get('priceUsd', 0) or 0)
                        market_cap = float(main_pair.get('marketCap', 0) or 0)
                        liquidity = float(main_pair.get('liquidity', {}).get('usd', 0) or 0)
                        volume_24h = float(main_pair.get('volume', {}).get('h24', 0) or 0)
                        
                        # Изменения цены
                        price_changes = {
                            '5m': float(main_pair.get('priceChange', {}).get('m5', 0) or 0),
                            '1h': float(main_pair.get('priceChange', {}).get('h1', 0) or 0),
                            '6h': float(main_pair.get('priceChange', {}).get('h6', 0) or 0),
                            '24h': float(main_pair.get('priceChange', {}).get('h24', 0) or 0)
                        }
                        
                        # Рассчитываем ROI сценарии
                        roi_scenarios = analyzer.calculate_roi_scenarios(current_price, entry_amounts)
                        
                        result = {
                            'token': token,
                            'tweet_impact': tweet_impact,
                            'market_data': {
                                'current_price': current_price,
                                'market_cap': market_cap,
                                'liquidity': liquidity,
                                'volume_24h': volume_24h,
                                'price_changes': price_changes
                            },
                            'roi_scenarios': roi_scenarios
                        }
                        
                        results.append(result)
                
                await asyncio.sleep(0.3)  # Пауза для API
        
        session.close()
        return results
        
    except Exception as e:
        logger.error(f"❌ Ошибка анализа: {e}")
        return []

def create_advanced_analysis_excel(results):
    """Создает расширенный Excel анализ"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"advanced_market_analysis_{timestamp}.xlsx"
        
        # 1. Основная таблица с корреляциями
        main_analysis = []
        
        # 2. Таблица входных точек и потенциальной прибыли
        profit_analysis = []
        
        # 3. Анализ по времени обнаружения
        discovery_time_analysis = []
        
        # 4. Статистика по категориям
        category_stats = {
            'discovery_categories': {},
            'tweet_activity': {},
            'volume_ranges': {},
            'price_performance': {}
        }
        
        for result in results:
            token = result['token']
            tweet_impact = result['tweet_impact']
            market_data = result['market_data']
            roi_scenarios = result['roi_scenarios']
            
            # Основная таблица
            main_row = {
                'Символ': token.symbol,
                'Название': token.name or 'N/A',
                'Адрес контракта': token.mint,
                
                # Данные о твитах
                'Твитов с контрактом': token.twitter_contract_tweets,
                'Твитов с символом': tweet_impact['total_symbol_tweets'],
                'Активность твитов': tweet_impact['tweet_activity'],
                
                # Время обнаружения
                'Время до обнаружения (ч)': f"{tweet_impact['time_to_discovery']:.1f}" if tweet_impact['time_to_discovery'] else 'N/A',
                'Категория обнаружения': tweet_impact['discovery_category'],
                'Возраст при обнаружении (ч)': f"{tweet_impact['token_age_at_discovery']:.1f}",
                
                # Рыночные данные
                'Текущая цена ($)': f"{market_data['current_price']:.10f}" if market_data['current_price'] else 'N/A',
                'Market Cap ($)': f"{market_data['market_cap']:,.0f}" if market_data['market_cap'] else 'N/A',
                'Ликвидность ($)': f"{market_data['liquidity']:,.0f}" if market_data['liquidity'] else 'N/A',
                'Объем 24ч ($)': f"{market_data['volume_24h']:,.0f}" if market_data['volume_24h'] else 'N/A',
                
                # Изменения цены
                'Изменение 5м (%)': f"{market_data['price_changes']['5m']:.2f}",
                'Изменение 1ч (%)': f"{market_data['price_changes']['1h']:.2f}",
                'Изменение 6ч (%)': f"{market_data['price_changes']['6h']:.2f}",
                'Изменение 24ч (%)': f"{market_data['price_changes']['24h']:.2f}",
                
                # Оценки
                'Эффективность обнаружения': 'Высокая' if tweet_impact['time_to_discovery'] and tweet_impact['time_to_discovery'] <= 6 else 'Средняя' if tweet_impact['time_to_discovery'] and tweet_impact['time_to_discovery'] <= 24 else 'Низкая',
                'Рыночная активность': 'Высокая' if market_data['volume_24h'] > 10000 else 'Средняя' if market_data['volume_24h'] > 1000 else 'Низкая',
                
                # Ссылки
                'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                'Pump.fun': f"https://pump.fun/{token.mint}"
            }
            main_analysis.append(main_row)
            
            # Анализ прибыльности для разных входов
            for amount, scenario in roi_scenarios.items():
                profit_row = {
                    'Символ': token.symbol,
                    'Вход ($)': amount,
                    'Куплено токенов': f"{scenario['tokens']:.6f}",
                    'Прибыль при 2x ($)': f"{scenario['roi_2x']:.2f}",
                    'Прибыль при 5x ($)': f"{scenario['roi_5x']:.2f}",
                    'Прибыль при 10x ($)': f"{scenario['roi_10x']:.2f}",
                    'Прибыль при 50x ($)': f"{scenario['roi_50x']:.2f}",
                    'Прибыль при 100x ($)': f"{scenario['roi_100x']:.2f}",
                    'Процент ROI при 2x': f"{scenario['percentage_2x']:.0f}%",
                    'Процент ROI при 10x': f"{scenario['percentage_10x']:.0f}%",
                    'Процент ROI при 100x': f"{scenario['percentage_100x']:.0f}%",
                    'Текущий объем 24ч': f"{market_data['volume_24h']:,.0f}",
                    'Ликвидность': f"{market_data['liquidity']:,.0f}",
                    'Изменение за 24ч': f"{market_data['price_changes']['24h']:.2f}%"
                }
                profit_analysis.append(profit_row)
            
            # Анализ времени обнаружения
            if tweet_impact['time_to_discovery'] is not None:
                discovery_row = {
                    'Символ': token.symbol,
                    'Время обнаружения (ч)': tweet_impact['time_to_discovery'],
                    'Категория': tweet_impact['discovery_category'],
                    'Объем через 24ч': market_data['volume_24h'],
                    'Изменение цены 24ч (%)': market_data['price_changes']['24h'],
                    'Market Cap': market_data['market_cap'],
                    'Эффективность': 'Отличная' if tweet_impact['time_to_discovery'] <= 1 and market_data['price_changes']['24h'] > 50 
                                   else 'Хорошая' if tweet_impact['time_to_discovery'] <= 6 and market_data['price_changes']['24h'] > 10
                                   else 'Средняя' if market_data['price_changes']['24h'] > 0 else 'Низкая'
                }
                discovery_time_analysis.append(discovery_row)
            
            # Сбор статистики
            cat = tweet_impact['discovery_category']
            category_stats['discovery_categories'][cat] = category_stats['discovery_categories'].get(cat, 0) + 1
            
            activity = tweet_impact['tweet_activity']
            category_stats['tweet_activity'][activity] = category_stats['tweet_activity'].get(activity, 0) + 1
        
        # Создаем DataFrame'ы
        main_df = pd.DataFrame(main_analysis)
        profit_df = pd.DataFrame(profit_analysis)
        discovery_df = pd.DataFrame(discovery_time_analysis)
        
        # Статистика
        stats_data = []
        
        # Статистика по категориям обнаружения
        for cat, count in category_stats['discovery_categories'].items():
            stats_data.append({
                'Категория': 'Скорость обнаружения',
                'Значение': cat,
                'Количество': count,
                'Процент': f"{(count/len(results)*100):.1f}%"
            })
        
        # Статистика по активности твитов
        for activity, count in category_stats['tweet_activity'].items():
            stats_data.append({
                'Категория': 'Активность твитов',
                'Значение': activity,
                'Количество': count,
                'Процент': f"{(count/len(results)*100):.1f}%"
            })
        
        stats_df = pd.DataFrame(stats_data)
        
        # Корреляционный анализ
        correlation_data = []
        if len(discovery_time_analysis) > 5:  # Достаточно данных для корреляции
            discovery_analysis_df = pd.DataFrame(discovery_time_analysis)
            
            # Корреляция между временем обнаружения и изменением цены
            time_price_corr = discovery_analysis_df['Время обнаружения (ч)'].corr(
                discovery_analysis_df['Изменение цены 24ч (%)']
            )
            
            correlation_data.append({
                'Переменная 1': 'Время обнаружения (ч)',
                'Переменная 2': 'Изменение цены 24ч (%)',
                'Корреляция': f"{time_price_corr:.4f}" if not pd.isna(time_price_corr) else 'N/A',
                'Интерпретация': 'Отрицательная корреляция - быстрое обнаружение связано с ростом цены' if time_price_corr < -0.1 
                                else 'Положительная корреляция - медленное обнаружение связано с ростом цены' if time_price_corr > 0.1
                                else 'Слабая корреляция'
            })
        
        correlation_df = pd.DataFrame(correlation_data)
        
        # Сохраняем в Excel
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name='Основной анализ', index=False)
            profit_df.to_excel(writer, sheet_name='Анализ прибыльности', index=False)
            discovery_df.to_excel(writer, sheet_name='Анализ времени', index=False)
            stats_df.to_excel(writer, sheet_name='Статистика', index=False)
            
            if not correlation_df.empty:
                correlation_df.to_excel(writer, sheet_name='Корреляции', index=False)
            
            # Автоподгонка ширины колонок
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
                
                worksheet.freeze_panes = 'A2'
        
        logger.info(f"✅ Продвинутый анализ сохранен в {filename}")
        return filename, len(results)
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания Excel: {e}")
        return None, 0

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск продвинутого анализа влияния твитов на рынок")
    
    # Анализируем влияние на рынок
    results = await analyze_market_impact()
    
    if not results:
        logger.error("❌ Нет результатов для анализа")
        return
    
    logger.info(f"📊 Проанализировано {len(results)} токенов")
    
    # Создаем расширенный отчет
    filename, count = create_advanced_analysis_excel(results)
    
    if filename:
        logger.info(f"📈 ПРОДВИНУТЫЙ АНАЛИЗ ЗАВЕРШЕН:")
        logger.info(f"  • Файл: {filename}")
        logger.info(f"  • Токенов проанализировано: {count}")
        
        # Быстрая статистика
        fast_discoveries = sum(1 for r in results if r['tweet_impact']['time_to_discovery'] and r['tweet_impact']['time_to_discovery'] <= 6)
        profitable_24h = sum(1 for r in results if r['market_data']['price_changes']['24h'] > 10)
        high_volume = sum(1 for r in results if r['market_data']['volume_24h'] > 10000)
        
        logger.info(f"  • Быстрых обнаружений (≤6ч): {fast_discoveries}")
        logger.info(f"  • Прибыльных за 24ч (>10%): {profitable_24h}")
        logger.info(f"  • С высоким объемом (>$10k): {high_volume}")
        
        # ТОП токены по эффективности
        effective_tokens = [r for r in results if r['tweet_impact']['time_to_discovery'] and 
                          r['tweet_impact']['time_to_discovery'] <= 6 and 
                          r['market_data']['price_changes']['24h'] > 20]
        
        if effective_tokens:
            logger.info(f"🏆 ТОП эффективных обнаружений (быстро + прибыльно):")
            for i, r in enumerate(sorted(effective_tokens, key=lambda x: x['market_data']['price_changes']['24h'], reverse=True)[:5], 1):
                symbol = r['token'].symbol
                time_discovery = r['tweet_impact']['time_to_discovery']
                price_change = r['market_data']['price_changes']['24h']
                logger.info(f"  {i}. {symbol}: обнаружен за {time_discovery:.1f}ч, рост {price_change:+.1f}%")
    
    logger.info("✅ Продвинутый анализ завершен!")

if __name__ == "__main__":
    asyncio.run(main())