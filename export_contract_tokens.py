#!/usr/bin/env python3
"""
Экспорт токенов с обнаруженными твитами по адресу контракта в Excel
"""

import pandas as pd
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv
from database import get_db_manager, Token
from logger_config import setup_logging

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

def export_contract_tokens_to_excel():
    """Экспортирует токены с найденными твитами по контракту в Excel"""
    session = None
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        logger.info("🔍 Поиск токенов с найденными твитами по адресу контракта...")
        
        # Ищем токены где найдены твиты с контрактом
        tokens = session.query(Token).filter(
            Token.twitter_contract_tweets > 0,  # Найдены твиты с контрактом
            Token.mint.isnot(None),             # Есть адрес контракта
            Token.symbol.isnot(None)            # Есть символ
        ).order_by(Token.twitter_contract_tweets.desc()).all()
        
        logger.info(f"📊 Найдено {len(tokens)} токенов с твитами по контракту")
        
        if not tokens:
            logger.warning("⚠️ Нет токенов с найденными твитами по контракту")
            return None
        
        # Подготавливаем данные для экспорта
        export_data = []
        
        for token in tokens:
            # Вычисляем возраст токена
            age_hours = (datetime.utcnow() - token.created_at).total_seconds() / 3600
            
            # Определяем время когда найден контракт
            time_to_find = None
            if token.updated_at and token.created_at:
                time_to_find_hours = (token.updated_at - token.created_at).total_seconds() / 3600
                time_to_find = f"{time_to_find_hours:.1f} ч"
            
            export_data.append({
                'Символ': token.symbol,
                'Название': token.name or 'N/A',
                'Адрес контракта': token.mint,
                'Твитов с контрактом': token.twitter_contract_tweets,
                'Market Cap ($)': f"{token.market_cap:,.0f}" if token.market_cap else 'N/A',
                'Возраст токена (ч)': f"{age_hours:.1f}",
                'Время до обнаружения': time_to_find or 'N/A',
                'Создан': token.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Обнаружен': token.updated_at.strftime('%Y-%m-%d %H:%M:%S') if token.updated_at else 'N/A',
                'Твиты символа': token.twitter_symbol_tweets or 0,
                'Общая активность': token.twitter_engagement or 0,
                'Twitter рейтинг': token.twitter_rating or 'N/A',
                'Twitter скор': f"{token.twitter_score:.2f}" if token.twitter_score else 'N/A',
                'Bonding Curve': token.bonding_curve_key or 'N/A',
                'Описание': (token.description or '')[:100] + '...' if token.description and len(token.description) > 100 else token.description or 'N/A',
                'Ссылки': f"https://pump.fun/{token.mint}",
                'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                'Axiom Trade': f"https://axiom.trade/meme/{token.bonding_curve_key or token.mint}"
            })
        
        # Создаем DataFrame
        df = pd.DataFrame(export_data)
        
        # Генерируем имя файла с текущей датой
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"contract_tokens_{timestamp}.xlsx"
        
        # Сохраняем в Excel с настройками
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Токены с контрактами', index=False)
            
            # Получаем лист для настройки форматирования
            worksheet = writer.sheets['Токены с контрактами']
            
            # Автоматически подгоняем ширину колонок
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                
                # Устанавливаем ширину колонки (максимум 50 символов)
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # Замораживаем первую строку (заголовки)
            worksheet.freeze_panes = 'A2'
        
        logger.info(f"✅ Данные экспортированы в файл: {filename}")
        logger.info(f"📊 Всего токенов: {len(tokens)}")
        
        # Статистика по экспорту
        total_tweets = sum(token.twitter_contract_tweets for token in tokens)
        avg_tweets = total_tweets / len(tokens) if tokens else 0
        
        logger.info(f"📈 Статистика:")
        logger.info(f"  • Всего твитов с контрактами: {total_tweets}")
        logger.info(f"  • Среднее твитов на токен: {avg_tweets:.1f}")
        logger.info(f"  • Максимум твитов: {max(token.twitter_contract_tweets for token in tokens)}")
        logger.info(f"  • Минимум твитов: {min(token.twitter_contract_tweets for token in tokens)}")
        
        return filename
        
    except Exception as e:
        logger.error(f"❌ Ошибка при экспорте: {e}")
        return None
    finally:
        if session:
            session.close()

def export_recent_contract_tokens(hours=24):
    """Экспортирует токены с найденными твитами за последние N часов"""
    session = None
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        logger.info(f"🔍 Поиск токенов с контрактами за последние {hours} часов...")
        
        # Ищем токены где найдены твиты с контрактом за последние N часов
        tokens = session.query(Token).filter(
            Token.twitter_contract_tweets > 0,  # Найдены твиты с контрактом
            Token.updated_at >= cutoff_time,    # Обновлены за последние N часов
            Token.mint.isnot(None),             # Есть адрес контракта
            Token.symbol.isnot(None)            # Есть символ
        ).order_by(Token.updated_at.desc()).all()
        
        logger.info(f"📊 Найдено {len(tokens)} токенов с контрактами за последние {hours} часов")
        
        if not tokens:
            logger.warning(f"⚠️ Нет токенов с контрактами за последние {hours} часов")
            return None
        
        # Подготавливаем данные (аналогично основной функции)
        export_data = []
        
        for token in tokens:
            age_hours = (datetime.utcnow() - token.created_at).total_seconds() / 3600
            time_to_find = None
            if token.updated_at and token.created_at:
                time_to_find_hours = (token.updated_at - token.created_at).total_seconds() / 3600
                time_to_find = f"{time_to_find_hours:.1f} ч"
            
            export_data.append({
                'Символ': token.symbol,
                'Название': token.name or 'N/A',
                'Адрес контракта': token.mint,
                'Твитов с контрактом': token.twitter_contract_tweets,
                'Market Cap ($)': f"{token.market_cap:,.0f}" if token.market_cap else 'N/A',
                'Возраст токена (ч)': f"{age_hours:.1f}",
                'Время до обнаружения': time_to_find or 'N/A',
                'Создан': token.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'Обнаружен': token.updated_at.strftime('%Y-%m-%d %H:%M:%S') if token.updated_at else 'N/A',
                'Твиты символа': token.twitter_symbol_tweets or 0,
                'Общая активность': token.twitter_engagement or 0,
                'Twitter рейтинг': token.twitter_rating or 'N/A',
                'Twitter скор': f"{token.twitter_score:.2f}" if token.twitter_score else 'N/A',
                'Bonding Curve': token.bonding_curve_key or 'N/A',
                'Описание': (token.description or '')[:100] + '...' if token.description and len(token.description) > 100 else token.description or 'N/A',
                'Ссылки': f"https://pump.fun/{token.mint}",
                'DexScreener': f"https://dexscreener.com/solana/{token.mint}",
                'Axiom Trade': f"https://axiom.trade/meme/{token.bonding_curve_key or token.mint}"
            })
        
        # Создаем DataFrame
        df = pd.DataFrame(export_data)
        
        # Генерируем имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"contract_tokens_last_{hours}h_{timestamp}.xlsx"
        
        # Сохраняем в Excel
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f'Контракты за {hours}ч', index=False)
            
            worksheet = writer.sheets[f'Контракты за {hours}ч']
            
            # Автоподгонка ширины колонок
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
        
        logger.info(f"✅ Данные за {hours} часов экспортированы в файл: {filename}")
        return filename
        
    except Exception as e:
        logger.error(f"❌ Ошибка при экспорте за {hours} часов: {e}")
        return None
    finally:
        if session:
            session.close()

def main():
    """Главная функция"""
    logger.info("🚀 Запуск экспорта токенов с найденными контрактами")
    
    # Экспорт всех токенов с контрактами
    filename1 = export_contract_tokens_to_excel()
    
    # Экспорт токенов за последние 24 часа
    filename2 = export_recent_contract_tokens(24)
    
    # Экспорт токенов за последние 6 часов
    filename3 = export_recent_contract_tokens(6)
    
    logger.info("📊 ИТОГОВЫЕ ФАЙЛЫ:")
    if filename1:
        logger.info(f"  • Все токены: {filename1}")
    if filename2:
        logger.info(f"  • За 24 часа: {filename2}")
    if filename3:
        logger.info(f"  • За 6 часов: {filename3}")
    
    logger.info("✅ Экспорт завершен!")

if __name__ == "__main__":
    main()