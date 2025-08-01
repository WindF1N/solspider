#!/usr/bin/env python3
"""
Анализ данных поведения токенов
Ищет паттерны volume bot marketing среди собранных данных
"""

import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import numpy as np
from typing import Dict, List, Tuple
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройка matplotlib для русского языка
plt.rcParams['font.size'] = 10
plt.style.use('seaborn-v0_8')

class TokenBehaviorAnalyzer:
    """Анализатор поведения токенов"""
    
    def __init__(self, data_dir: str = "token_behavior_data"):
        self.data_dir = Path(data_dir)
        self.analysis_dir = Path("behavior_analysis")
        self.analysis_dir.mkdir(exist_ok=True)
        
    def load_token_data(self, token_address: str) -> pd.DataFrame:
        """Загружает все данные по токену"""
        token_dir = self.data_dir / token_address
        
        if not token_dir.exists():
            logger.warning(f"⚠️ Папка токена {token_address[:8]}... не найдена")
            return pd.DataFrame()
        
        data_files = list(token_dir.glob("token_data_*.json"))
        
        if not data_files:
            logger.warning(f"⚠️ Файлы данных для токена {token_address[:8]}... не найдены")
            return pd.DataFrame()
        
        all_data = []
        
        for file_path in sorted(data_files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_data.append(data)
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {file_path}: {e}")
        
        if not all_data:
            return pd.DataFrame()
        
        # Создаем DataFrame
        df = pd.DataFrame(all_data)
        
        # Конвертируем timestamp в datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"✅ Загружено {len(df)} записей для токена {token_address[:8]}...")
        return df
    
    def detect_volume_bot_patterns(self, df: pd.DataFrame) -> Dict:
        """Определяет паттерны volume bot marketing"""
        if df.empty:
            return {}
        
        patterns = {
            'suspicious_bundler_spikes': [],
            'coordinated_activity': [],
            'whale_concentration': [],
            'rapid_holder_changes': [],
            'liquidity_manipulation': []
        }
        
        # 1. Анализ бандлеров
        if 'bundlers_percentage' in df.columns:
            bundler_values = df['bundlers_percentage'].fillna(0)
            
            # Подозрительные скачки бандлеров
            bundler_spikes = []
            for i in range(1, len(bundler_values)):
                if bundler_values.iloc[i] - bundler_values.iloc[i-1] > 15:  # Скачок > 15%
                    bundler_spikes.append({
                        'timestamp': df.iloc[i]['timestamp'],
                        'jump': bundler_values.iloc[i] - bundler_values.iloc[i-1],
                        'value_before': bundler_values.iloc[i-1],
                        'value_after': bundler_values.iloc[i]
                    })
            
            patterns['suspicious_bundler_spikes'] = bundler_spikes
        
        # 2. Анализ холдеров
        if 'holders_count' in df.columns:
            holders = df['holders_count'].fillna(0)
            
            # Быстрые изменения количества холдеров
            rapid_changes = []
            for i in range(1, len(holders)):
                if abs(holders.iloc[i] - holders.iloc[i-1]) > 50:  # Изменение > 50 холдеров за интервал
                    rapid_changes.append({
                        'timestamp': df.iloc[i]['timestamp'],
                        'change': holders.iloc[i] - holders.iloc[i-1],
                        'holders_before': holders.iloc[i-1],
                        'holders_after': holders.iloc[i]
                    })
            
            patterns['rapid_holder_changes'] = rapid_changes
        
        # 3. Анализ ликвидности (SOL)
        if 'liquidity_sol' in df.columns:
            liquidity = df['liquidity_sol'].fillna(0)
            
            # Подозрительные манипуляции с ликвидностью
            liq_changes = []
            for i in range(1, len(liquidity)):
                if liquidity.iloc[i-1] > 0:  # Избегаем деления на 0
                    pct_change = abs(liquidity.iloc[i] - liquidity.iloc[i-1]) / liquidity.iloc[i-1] * 100
                    if pct_change > 200:  # Изменение > 200%
                        liq_changes.append({
                            'timestamp': df.iloc[i]['timestamp'],
                            'pct_change': pct_change,
                            'liquidity_before': liquidity.iloc[i-1],
                            'liquidity_after': liquidity.iloc[i]
                        })
            
            patterns['liquidity_manipulation'] = liq_changes
        
        # 4. Анализ топ холдеров (концентрация)
        if 'top10_holders_percent' in df.columns:
            top10_values = df['top10_holders_percent'].fillna(0)
            
            for i, row in df.iterrows():
                top10_concentration = row['top10_holders_percent']
                if top10_concentration > 60:  # Топ-10 холдеров > 60%
                    patterns['whale_concentration'].append({
                        'timestamp': row['timestamp'],
                        'top10_concentration': top10_concentration
                    })
        
        # 5. Анализ процента ботов
        if 'bot_percentage' in df.columns:
            bot_values = df['bot_percentage'].fillna(0)
            
            for i, row in df.iterrows():
                bot_pct = row['bot_percentage']
                if bot_pct > 60:  # Ботов > 60%
                    patterns['coordinated_activity'].append({
                        'timestamp': row['timestamp'],
                        'bot_percentage': bot_pct,
                        'bot_users_count': row.get('bot_users_count', 0),
                        'holders_count': row.get('holders_count', 0)
                    })
        
        return patterns
    
    def calculate_risk_score(self, patterns: Dict, df: pd.DataFrame) -> float:
        """Рассчитывает общий риск-скор токена"""
        score = 0
        
        # Бандлеры
        if patterns['suspicious_bundler_spikes']:
            score += len(patterns['suspicious_bundler_spikes']) * 20
        
        # Быстрые изменения холдеров
        if patterns['rapid_holder_changes']:
            score += len(patterns['rapid_holder_changes']) * 10
        
        # Манипуляции с ликвидностью
        if patterns['liquidity_manipulation']:
            score += len(patterns['liquidity_manipulation']) * 15
        
        # Концентрация китов
        if patterns['whale_concentration']:
            score += len(patterns['whale_concentration']) * 25
        
        # Координированная активность ботов
        if patterns['coordinated_activity']:
            score += len(patterns['coordinated_activity']) * 30
        
        # Дополнительные критерии
        if not df.empty:
            # Высокий постоянный процент бандлеров
            if 'bundlers_percentage' in df.columns:
                avg_bundlers = df['bundlers_percentage'].fillna(0).mean()
                if avg_bundlers > 20:
                    score += 40  # Повышенный вес для bundlers
                elif avg_bundlers > 10:
                    score += 25
                elif avg_bundlers > 5:
                    score += 15
            
            # Высокий процент инсайдеров
            if 'insiders_percentage' in df.columns:
                avg_insiders = df['insiders_percentage'].fillna(0).mean()
                if avg_insiders > 15:
                    score += 30
                elif avg_insiders > 8:
                    score += 20
            
            # Высокий процент ботов
            if 'bot_percentage' in df.columns:
                avg_bots = df['bot_percentage'].fillna(0).mean()
                if avg_bots > 60:
                    score += 35
                elif avg_bots > 40:
                    score += 25
                elif avg_bots > 25:
                    score += 15
            
            # Высокая концентрация топ-10 холдеров
            if 'top10_holders_percent' in df.columns:
                avg_top10 = df['top10_holders_percent'].fillna(0).mean()
                if avg_top10 > 70:
                    score += 30
                elif avg_top10 > 50:
                    score += 20
            
            # DEX не оплачен (красный флаг)
            if 'dex_paid' in df.columns:
                dex_paid_count = df['dex_paid'].fillna(False).sum()
                total_records = len(df)
                if dex_paid_count / total_records < 0.5:  # Меньше 50% записей с оплаченным DEX
                    score += 25
        
        return min(score, 100)  # Максимум 100
    
    def create_token_report(self, token_address: str) -> Dict:
        """Создает подробный отчет по токену"""
        df = self.load_token_data(token_address)
        
        if df.empty:
            return {'error': 'Нет данных для анализа'}
        
        patterns = self.detect_volume_bot_patterns(df)
        risk_score = self.calculate_risk_score(patterns, df)
        
        # Статистика
        stats = {}
        
        if 'bundlers_percentage' in df.columns:
            stats['bundlers'] = {
                'avg': df['bundlers_percentage'].fillna(0).mean(),
                'max': df['bundlers_percentage'].fillna(0).max(),
                'min': df['bundlers_percentage'].fillna(0).min()
            }
        
        if 'holders_count' in df.columns:
            stats['holders'] = {
                'avg': df['holders_count'].fillna(0).mean(),
                'max': df['holders_count'].fillna(0).max(),
                'min': df['holders_count'].fillna(0).min(),
                'growth': df['holders_count'].fillna(0).iloc[-1] - df['holders_count'].fillna(0).iloc[0] if len(df) > 1 else 0
            }
        
        if 'liquidity_sol' in df.columns:
            stats['liquidity_sol'] = {
                'avg': df['liquidity_sol'].fillna(0).mean(),
                'max': df['liquidity_sol'].fillna(0).max(),
                'min': df['liquidity_sol'].fillna(0).min()
            }
        
        if 'bot_percentage' in df.columns:
            stats['bots'] = {
                'avg': df['bot_percentage'].fillna(0).mean(),
                'max': df['bot_percentage'].fillna(0).max(),
                'min': df['bot_percentage'].fillna(0).min()
            }
        
        if 'insiders_percentage' in df.columns:
            stats['insiders'] = {
                'avg': df['insiders_percentage'].fillna(0).mean(),
                'max': df['insiders_percentage'].fillna(0).max(),
                'min': df['insiders_percentage'].fillna(0).min()
            }
        
        if 'top10_holders_percent' in df.columns:
            stats['top10_holders'] = {
                'avg': df['top10_holders_percent'].fillna(0).mean(),
                'max': df['top10_holders_percent'].fillna(0).max(),
                'min': df['top10_holders_percent'].fillna(0).min()
            }
        
        if 'dex_paid' in df.columns:
            dex_paid_count = df['dex_paid'].fillna(False).sum()
            stats['dex_paid'] = {
                'total_records': len(df),
                'paid_count': int(dex_paid_count),
                'paid_percentage': (dex_paid_count / len(df)) * 100 if len(df) > 0 else 0
            }
        
        report = {
            'token_address': token_address,
            'analysis_timestamp': datetime.now().isoformat(),
            'data_points': len(df),
            'monitoring_duration': str(df['timestamp'].max() - df['timestamp'].min()) if len(df) > 1 else '0:00:00',
            'risk_score': risk_score,
            'risk_level': self.get_risk_level(risk_score),
            'suspicious_patterns': patterns,
            'statistics': stats,
            'recommendations': self.get_recommendations(risk_score, patterns)
        }
        
        return report
    
    def get_risk_level(self, score: float) -> str:
        """Определяет уровень риска"""
        if score >= 80:
            return "🔴 КРИТИЧЕСКИЙ - Очень высокая вероятность volume bot marketing"
        elif score >= 60:
            return "🟠 ВЫСОКИЙ - Подозрительная активность"
        elif score >= 40:
            return "🟡 СРЕДНИЙ - Некоторые признаки манипуляций"
        elif score >= 20:
            return "🟢 НИЗКИЙ - Минимальные подозрения"
        else:
            return "✅ НОРМАЛЬНЫЙ - Нет признаков манипуляций"
    
    def get_recommendations(self, score: float, patterns: Dict) -> List[str]:
        """Генерирует рекомендации"""
        recommendations = []
        
        if score >= 60:
            recommendations.append("❌ НЕ РЕКОМЕНДУЕТСЯ к инвестированию")
            recommendations.append("🔍 Требуется дополнительное исследование")
        
        if patterns['suspicious_bundler_spikes']:
            recommendations.append("⚠️ Обнаружены подозрительные скачки бандлеров")
        
        if patterns['whale_concentration']:
            recommendations.append("🐋 Высокая концентрация среди топ-10 холдеров")
        
        if patterns['coordinated_activity']:
            recommendations.append("🤖 Обнаружена координированная активность ботов")
        
        if patterns['liquidity_manipulation']:
            recommendations.append("💧 Возможны манипуляции с ликвидностью")
        
        if score < 40:
            recommendations.append("✅ Токен выглядит относительно безопасно")
        
        return recommendations
    
    def create_visualization(self, token_address: str):
        """Создает визуализацию данных токена"""
        df = self.load_token_data(token_address)
        
        if df.empty:
            logger.warning(f"⚠️ Нет данных для визуализации токена {token_address[:8]}...")
            return
        
        # Создаем фигуру с несколькими графиками
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'Анализ поведения токена {token_address[:8]}...', fontsize=16)
        
        # График 1: Бандлеры и снайперы
        if 'bundlers_percentage' in df.columns and 'snipers_percentage' in df.columns:
            axes[0, 0].plot(df['timestamp'], df['bundlers_percentage'].fillna(0), label='Bundlers %', color='red', linewidth=2)
            axes[0, 0].plot(df['timestamp'], df['snipers_percentage'].fillna(0), label='Snipers %', color='orange', linewidth=2)
            axes[0, 0].set_title('Bundlers и Snipers %')
            axes[0, 0].set_ylabel('Процент')
            axes[0, 0].legend()
            axes[0, 0].grid(True, alpha=0.3)
        
        # График 2: Количество холдеров
        if 'holders_count' in df.columns:
            axes[0, 1].plot(df['timestamp'], df['holders_count'].fillna(0), label='Holders', color='blue', linewidth=2)
            axes[0, 1].set_title('Количество холдеров')
            axes[0, 1].set_ylabel('Холдеры')
            axes[0, 1].grid(True, alpha=0.3)
        
        # График 3: Ликвидность
        if 'liquidity_usd' in df.columns:
            axes[1, 0].plot(df['timestamp'], df['liquidity_usd'].fillna(0), label='Liquidity USD', color='green', linewidth=2)
            axes[1, 0].set_title('Ликвидность (USD)')
            axes[1, 0].set_ylabel('USD')
            axes[1, 0].grid(True, alpha=0.3)
        
        # График 4: Процент разработчика
        if 'dev_percentage' in df.columns:
            axes[1, 1].plot(df['timestamp'], df['dev_percentage'].fillna(0), label='Dev %', color='purple', linewidth=2)
            axes[1, 1].set_title('Процент разработчика')
            axes[1, 1].set_ylabel('Процент')
            axes[1, 1].grid(True, alpha=0.3)
        
        # Поворачиваем подписи времени
        for ax in axes.flat:
            ax.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        
        # Сохраняем график
        output_path = self.analysis_dir / f"token_analysis_{token_address[:8]}.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"📊 График сохранен: {output_path}")
    
    def analyze_all_tokens(self) -> pd.DataFrame:
        """Анализирует все токены и создает сводный отчет"""
        if not self.data_dir.exists():
            logger.error("❌ Папка с данными не найдена")
            return pd.DataFrame()
        
        token_dirs = [d for d in self.data_dir.iterdir() if d.is_dir()]
        
        if not token_dirs:
            logger.error("❌ Токены для анализа не найдены")
            return pd.DataFrame()
        
        all_reports = []
        
        for token_dir in token_dirs:
            token_address = token_dir.name
            logger.info(f"🔍 Анализируем токен {token_address[:8]}...")
            
            try:
                report = self.create_token_report(token_address)
                
                if 'error' not in report:
                    # Создаем визуализацию
                    self.create_visualization(token_address)
                    
                    # Сохраняем подробный отчет
                    report_path = self.analysis_dir / f"report_{token_address[:8]}.json"
                    with open(report_path, 'w', encoding='utf-8') as f:
                        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
                    
                    # Добавляем в сводку
                    summary = {
                        'token_address': token_address,
                        'risk_score': report['risk_score'],
                        'risk_level': report['risk_level'],
                        'data_points': report['data_points'],
                        'monitoring_duration': report['monitoring_duration'],
                        'bundler_spikes': len(report['suspicious_patterns']['suspicious_bundler_spikes']),
                        'liquidity_manipulations': len(report['suspicious_patterns']['liquidity_manipulation']),
                        'whale_concentrations': len(report['suspicious_patterns']['whale_concentration'])
                    }
                    
                    all_reports.append(summary)
                    
            except Exception as e:
                logger.error(f"❌ Ошибка анализа токена {token_address[:8]}...: {e}")
        
        # Создаем сводный DataFrame
        summary_df = pd.DataFrame(all_reports)
        
        if not summary_df.empty:
            # Сортируем по риск-скору
            summary_df = summary_df.sort_values('risk_score', ascending=False)
            
            # Сохраняем сводный отчет
            summary_path = self.analysis_dir / "tokens_summary.csv"
            summary_df.to_csv(summary_path, index=False, encoding='utf-8')
            
            logger.info(f"📋 Сводный отчет сохранен: {summary_path}")
            logger.info(f"🔍 Проанализировано токенов: {len(summary_df)}")
            
            # Выводим топ подозрительных токенов
            logger.info("\n🚨 ТОП ПОДОЗРИТЕЛЬНЫХ ТОКЕНОВ:")
            for i, row in summary_df.head(5).iterrows():
                logger.info(f"  {row['token_address'][:8]}... - Риск: {row['risk_score']:.1f} - {row['risk_level']}")
        
        return summary_df

def main():
    """Основная функция"""
    logger.info("🔍 Запуск анализа поведения токенов...")
    
    analyzer = TokenBehaviorAnalyzer()
    
    # Анализируем все токены
    summary = analyzer.analyze_all_tokens()
    
    if not summary.empty:
        logger.info("✅ Анализ завершен успешно")
        logger.info(f"📊 Файлы анализа сохранены в папку: {analyzer.analysis_dir}")
    else:
        logger.warning("⚠️ Нет данных для анализа")

if __name__ == "__main__":
    main() 