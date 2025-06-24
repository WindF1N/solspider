#!/usr/bin/env python3
"""
Тестирование покупки и быстрой продажи через Axiom.trade API
"""

import asyncio
import logging
from axiom_trader import AxiomTrader

class AxiomTradingTest:
    def __init__(self):
        self.trader = AxiomTrader()
        
        # Настраиваем логирование
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    async def run_buy_sell_test(self):
        """Основной тест покупки и продажи"""
        try:
            self.logger.info("🧪 ТЕСТИРОВАНИЕ ПОКУПКИ И ПРОДАЖИ ЧЕРЕЗ AXIOM")
            self.logger.info("="*55)
            
            # Параметры теста
            test_token = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # BONK
            buy_amount_sol = 0.001  # ~$0.14 при цене SOL $140
            
            self.logger.info(f"🎯 Тестовый токен: BONK")
            self.logger.info(f"📍 Контракт: {test_token}")
            self.logger.info(f"💰 Сумма покупки: {buy_amount_sol} SOL")
            
            # Шаг 1: Покупка
            self.logger.info(f"\n🛒 ШАГ 1: ПОКУПКА")
            self.logger.info("-" * 30)
            
            buy_result = await self.trader.buy_token(
                token_address=test_token,
                sol_amount=buy_amount_sol
            )
            
            if not buy_result['success']:
                self.logger.error("❌ Покупка не удалась, прерываем тест")
                self.logger.error(f"   Ошибка: {buy_result.get('error', 'Неизвестная ошибка')}")
                return False
            
            # Анализируем ответ покупки
            response_data = buy_result.get('response', {})
            swap_params = response_data.get('getSwapParams', {})
            
            self.logger.info("✅ ПОКУПКА ВЫПОЛНЕНА УСПЕШНО!")
            self.logger.info(f"   ⏱️  Время выполнения: {buy_result['execution_time']:.2f}с")
            self.logger.info(f"   📊 Статус: {buy_result['status']}")
            
            if swap_params:
                input_mint = swap_params.get('inputMint')
                output_mint = swap_params.get('outputMint')
                amount = swap_params.get('amount')
                slippage = swap_params.get('slippage')
                
                self.logger.info(f"   💱 Swap параметры:")
                self.logger.info(f"      🪙 Input: {input_mint[:8]}...")
                self.logger.info(f"      🪙 Output: {output_mint[:8]}...")
                self.logger.info(f"      💰 Amount: {amount} lamports")
                self.logger.info(f"      📊 Slippage: {slippage}%")
            
            # Ждем выполнения покупки
            self.logger.info("\n⏳ Ждем выполнения покупки (10 секунд)...")
            await asyncio.sleep(10)
            
            # Шаг 2: Продажа
            self.logger.info(f"\n📉 ШАГ 2: ПРОДАЖА")
            self.logger.info("-" * 30)
            
            sell_result = await self.trader.sell_token(
                token_address=test_token,
                percentage=100  # Продаем 100% баланса
            )
            
            if sell_result['success']:
                # Анализируем ответ продажи
                response_data = sell_result.get('response', {})
                swap_params = response_data.get('getSwapParams', {})
                
                self.logger.info("✅ ПРОДАЖА ВЫПОЛНЕНА УСПЕШНО!")
                self.logger.info(f"   ⏱️  Время выполнения: {sell_result['execution_time']:.2f}с")
                self.logger.info(f"   📊 Статус: {sell_result['status']}")
                
                if swap_params:
                    input_mint = swap_params.get('inputMint')
                    output_mint = swap_params.get('outputMint')
                    amount = swap_params.get('amount')
                    slippage = swap_params.get('slippage')
                    
                    self.logger.info(f"   💱 Swap параметры:")
                    self.logger.info(f"      🪙 Input: {input_mint[:8]}...")
                    self.logger.info(f"      🪙 Output: {output_mint[:8]}...")
                    self.logger.info(f"      💰 Amount: {amount} токенов")
                    self.logger.info(f"      📊 Slippage: {slippage}%")
                
                # Расчет производительности
                total_time = buy_result['execution_time'] + sell_result['execution_time']
                self.logger.info(f"\n⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:")
                self.logger.info(f"   🛒 Время покупки: {buy_result['execution_time']:.2f}с")
                self.logger.info(f"   📉 Время продажи: {sell_result['execution_time']:.2f}с")
                self.logger.info(f"   🏆 Общее время: {total_time:.2f}с")
                
            else:
                self.logger.error("❌ Продажа не удалась")
                self.logger.error(f"   Ошибка: {sell_result.get('error', 'Неизвестная ошибка')}")
            
            self.logger.info("\n" + "="*55)
            self.logger.info("📊 ТЕСТ ЗАВЕРШЕН")
            self.logger.info("="*55)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка теста: {e}")
            return False

async def main():
    """Главная функция"""
    print("🚀 ТЕСТ ПОКУПКИ И ПРОДАЖИ ЧЕРЕЗ AXIOM.TRADE")
    print("="*60)
    print("⚠️  ВНИМАНИЕ: Это реальная торговля с реальными деньгами!")
    print("💰 Сумма теста: ~$0.14 (0.001 SOL)")
    print("🪙 Токен: BONK (высокая ликвидность)")
    print("⚡ Платформа: Axiom.trade (быстрая)")
    print("🎯 Ожидаемая скорость: <1 секунды на операцию")
    print("="*60)
    
    # Спрашиваем подтверждение
    confirm = input("\nПродолжить тест покупки и продажи? (yes/no): ").lower().strip()
    
    if confirm in ['yes', 'y', 'да', 'д']:
        print("\n🚀 Запускаем тест...\n")
        
        test = AxiomTradingTest()
        result = await test.run_buy_sell_test()
        
        if result:
            print("\n✅ Тест завершен успешно!")
            print("🎉 Axiom.trade показал отличную производительность!")
        else:
            print("\n❌ Тест завершен с ошибками")
    else:
        print("❌ Тест отменен пользователем")

if __name__ == "__main__":
    asyncio.run(main()) 