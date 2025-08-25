#!/bin/bash

# Создаем папку если не существует
mkdir -p null_snipers

count=0

for file in tokens_logs/*.log; do
    # Извлекаем последнюю запись о снайперах
    last_sniper=$(grep "Снайперы:" "$file" | tail -1)
    
    # Проверяем формат "0.0% (0)"
    if [[ "$last_sniper" =~ Снайперы:\ 0\.0%\ \(0\) ]]; then
        cp "$file" null_snipers/
        ((count++))
        echo "✓ $file: $last_sniper"
    fi
done

echo "===================================="
echo "Файлов с последними Снайперами: 0.0% (0): $count"
