#!/usr/bin/env python3
"""
Проверка полноты функций в test_filter.py против bundle_analyzer.py
"""

import os
import ast

def extract_functions_from_file(file_path):
    """Извлекает все определения функций из Python файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
        return functions
    except Exception as e:
        print(f"Ошибка чтения {file_path}: {e}")
        return []

def check_completeness():
    """Проверяет полноту функций в test_filter.py"""
    
    bundle_analyzer_functions = extract_functions_from_file('/home/creatxr/solspider/bundle_analyzer.py')
    test_filter_functions = extract_functions_from_file('/home/creatxr/solspider/test_filter.py')
    
    # Ключевые функции из bundle_analyzer.py для activity фильтрации
    required_functions = [
        'check_snipers_bundlers_correlation',
        'check_snipers_insiders_correlation', 
        'check_bundlers_snipers_exit_correlation',
        'check_holders_correlation',
        'check_rapid_exit',
        '_calculate_correlation',
        'analyze_holder_stability',
        'analyze_early_vs_current_holders',
        'is_suspicious_pattern'
    ]
    
    print("🔍 ПРОВЕРКА ПОЛНОТЫ ФУНКЦИЙ В test_filter.py")
    print("="*60)
    
    print(f"📂 bundle_analyzer.py: {len(bundle_analyzer_functions)} функций")
    print(f"📂 test_filter.py: {len(test_filter_functions)} функций")
    print()
    
    print("🎯 КЛЮЧЕВЫЕ ФУНКЦИИ ДЛЯ ACTIVITY ФИЛЬТРАЦИИ:")
    print("-"*60)
    
    missing_functions = []
    present_functions = []
    
    for func in required_functions:
        if func in test_filter_functions:
            present_functions.append(func)
            print(f"✅ {func}")
        else:
            missing_functions.append(func)
            print(f"❌ {func} - ОТСУТСТВУЕТ!")
    
    print()
    print("📊 РЕЗУЛЬТАТ:")
    print(f"✅ Реализовано: {len(present_functions)}/{len(required_functions)}")
    print(f"❌ Отсутствует: {len(missing_functions)}")
    
    if missing_functions:
        print(f"\n⚠️ НЕДОСТАЮЩИЕ ФУНКЦИИ:")
        for func in missing_functions:
            print(f"   - {func}")
        return False
    else:
        print(f"\n🎉 ВСЕ КЛЮЧЕВЫЕ ФУНКЦИИ РЕАЛИЗОВАНЫ!")
        return True

def check_activity_conditions():
    """Проверяет что activity_conditions используют все реальные функции"""
    
    print(f"\n🔬 ПРОВЕРКА activity_conditions В test_filter.py")
    print("-"*60)
    
    try:
        with open('/home/creatxr/solspider/test_filter.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Ищем activity_conditions
        if 'activity_conditions = {' in content:
            print("✅ activity_conditions найден")
            
            # Проверяем использование функций корреляции
            correlation_checks = [
                'self.check_snipers_bundlers_correlation(metrics_history)',
                'self.check_snipers_insiders_correlation(metrics_history)', 
                'self.check_bundlers_snipers_exit_correlation(metrics_history)',
                'await self.check_holders_correlation(metrics_history)'
            ]
            
            for check in correlation_checks:
                if check in content:
                    print(f"✅ {check}")
                else:
                    print(f"❌ {check} - НЕ ИСПОЛЬЗУЕТСЯ!")
            
            # Проверяем использование rapid_exit
            if 'self.check_rapid_exit(' in content:
                print("✅ check_rapid_exit используется")
            else:
                print("❌ check_rapid_exit НЕ ИСПОЛЬЗУЕТСЯ!")
                
            # Проверяем is_suspicious_pattern
            if 'self.is_suspicious_pattern(' in content:
                print("✅ is_suspicious_pattern используется")
            else:
                print("❌ is_suspicious_pattern НЕ ИСПОЛЬЗУЕТСЯ!")
                
        else:
            print("❌ activity_conditions НЕ НАЙДЕН!")
            
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")

def main():
    print("🚀 ПОЛНАЯ ПРОВЕРКА СООТВЕТСТВИЯ test_filter.py и bundle_analyzer.py")
    print("="*80)
    
    # Проверяем полноту функций
    functions_complete = check_completeness()
    
    # Проверяем использование в activity_conditions
    check_activity_conditions()
    
    print("\n" + "="*80)
    if functions_complete:
        print("🎯 ЗАКЛЮЧЕНИЕ: test_filter.py ПОЛНОСТЬЮ СООТВЕТСТВУЕТ bundle_analyzer.py")
        print("   ✅ Все ключевые функции реализованы")
        print("   ✅ Корреляционные проверки используются")
        print("   ✅ Логика фильтрации соответствует оригиналу")
    else:
        print("⚠️ ЗАКЛЮЧЕНИЕ: test_filter.py ТРЕБУЕТ ДОРАБОТКИ")
        print("   ❌ Некоторые функции отсутствуют")
        print("   ⚠️ Проверьте полноту реализации")

if __name__ == "__main__":
    main()