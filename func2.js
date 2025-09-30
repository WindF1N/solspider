// Исправленная версия с корректными параметрами для запроса свечей
async function collectTransactions() {
    const baseUrl = 'https://gmgn.ai/vas/api/v1/token_trades/sol/LpKR28oxerMtdUBaPnXbA6Rmi5mF1irQQhrBFAkpump';
    const candlesUrl = 'https://gmgn.ai/api/v1/token_mcap_candles/sol/LpKR28oxerMtdUBaPnXbA6Rmi5mF1irQQhrBFAkpump';
    
    const params = {
        device_id: 'b93aa0d1-a85e-4d5c-be57-c58a5932fce7',
        fp_did: '76c9f7989ab9b34edbced17d43064d5f',
        client_id: 'gmgn_web_20250926-4643-32dc122',
        from_app: 'gmgn',
        app_ver: '20250926-4643-32dc122',
        tz_name: 'Europe/Samara',
        tz_offset: '14400',
        app_lang: 'ru',
        os: 'web',
        limit: '50',
        maker: ''
    };

    let allTransactions = [];
    const from = 1758910663;
    const to = 1758937972;
    
    // Статистика
    let stats = {
        totalSeconds: 0,
        secondsWithTransactions: 0,
        transactionsPerSecond: [],
        startTime: Date.now(),
        totalTransactions: 0,
        candlesCount: 0,
        // Новая статистика по объему
        volumeStats: {
            totalVolume: 0,
            volumePerTransaction: 0,
            volumePerSecond: 0,
            volumePerCandle: 0,
            maxVolumePerCandle: 0,
            candlesData: [] // данные по свечам
        }
    };

    console.log(`Начало сбора данных с ${from} по ${to}`);
    console.log('========================================');

    // Шаг 1: Получаем список секунд со свечами
    console.log('Получаем список секунд с активностью...');
    
    const candlesParams = new URLSearchParams({
        device_id: params.device_id,
        fp_did: params.fp_did,
        client_id: params.client_id,
        from_app: params.from_app,
        app_ver: params.app_ver,
        tz_name: params.tz_name,
        tz_offset: params.tz_offset,
        app_lang: params.app_lang,
        os: params.os,
        resolution: '1s',
        from: (from * 1000).toString(), // начало диапазона в миллисекундах
        to: (to * 1000).toString(),     // конец диапазона в миллисекундах
        limit: '500',
        pool_type: 'unified'
    });

    try {
        const candlesResponse = await fetch(`${candlesUrl}?${candlesParams.toString()}`);
        const candlesData = await candlesResponse.json();
        
        console.log('Ответ от API свечей:', candlesData);
        
        if (candlesData.code === 0 && candlesData.data && candlesData.data.list) {
            // Сохраняем данные свечей для статистики объема
            stats.volumeStats.candlesData = candlesData.data.list;
            
            // Извлекаем секунды из timestamp (делим на 1000)
            const activeSeconds = candlesData.data.list.map(candle => 
                Math.floor(candle.time / 1000)
            ).filter(second => second >= from && second <= to);
            
            stats.candlesCount = activeSeconds.length;
            console.log(`Найдено ${activeSeconds.length} секунд с активностью`);
            
            if (activeSeconds.length === 0) {
                console.log('Нет активных секунд в указанном диапазоне');
                return { transactions: [], statistics: stats };
            }
            
            // Шаг 2: Запрашиваем транзакции только для активных секунд
            console.log('Начинаем сбор транзакций для активных секунд...');
            
            for (let i = 0; i < activeSeconds.length; i++) {
                const current = activeSeconds[i];
                const urlParams = new URLSearchParams({
                    ...params,
                    from: current.toString(),
                    to: current.toString()
                });

                const url = `${baseUrl}?${urlParams.toString()}`;
                
                try {
                    const response = await fetch(url);
                    const data = await response.json();
                    
                    let transactionsThisSecond = 0;
                    let volumeThisSecond = 0;
                    
                    if (data.code === 0 && data.data && data.data.history) {
                        const newTransactions = data.data.history.filter(
                            t => !allTransactions.some(existing => existing.id === t.id)
                        );
                        transactionsThisSecond = newTransactions.length;
                        
                        // Считаем объем для новых транзакций
                        volumeThisSecond = newTransactions.reduce((sum, transaction) => {
                            return sum + parseFloat(transaction.amount_usd || 0);
                        }, 0);
                        
                        allTransactions.push(...newTransactions);
                        
                        // Обновляем статистику
                        stats.totalSeconds++;
                        stats.totalTransactions = allTransactions.length;
                        stats.volumeStats.totalVolume += volumeThisSecond;
                        
                        if (transactionsThisSecond > 0) {
                            stats.secondsWithTransactions++;
                            stats.transactionsPerSecond.push({
                                second: current,
                                count: transactionsThisSecond,
                                volume: volumeThisSecond
                            });
                        }
                        
                        console.log(`[${i+1}/${activeSeconds.length}] Секунда ${current}: ${transactionsThisSecond} транз/сек, объем: $${volumeThisSecond.toFixed(2)} | Всего: ${allTransactions.length} транзакций`);
                    } else {
                        console.log(`[${i+1}/${activeSeconds.length}] Секунда ${current}: 0 транз/сек | Всего: ${allTransactions.length} транзакций`);
                        stats.totalSeconds++;
                    }
                    
                    // Пауза 1 секунда между запросами
                    if (i < activeSeconds.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                    
                } catch (error) {
                    console.error(`Ошибка на секунде ${current}:`, error);
                    stats.totalSeconds++;
                    if (i < activeSeconds.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, 1000));
                    }
                }
            }
        } else {
            console.error('Ошибка при получении свечей:', candlesData.message || 'Неизвестная ошибка');
            
            // Если не удалось получить свечи, используем старый метод (по всем секундам)
            console.log('Используем резервный метод: сбор по всем секундам...');
            return await collectTransactionsFallback(from, to);
        }
    } catch (error) {
        console.error('Ошибка при запросе свечей:', error);
        
        // Резервный метод
        console.log('Используем резервный метод: сбор по всем секундам...');
        return await collectTransactionsFallback(from, to);
    }

    // Финальная статистика и вывод
    return generateFinalReport(allTransactions, stats);
}

// Резервный метод: сбор по всем секундам
async function collectTransactionsFallback(from, to) {
    const baseUrl = 'https://gmgn.ai/vas/api/v1/token_trades/sol/rbPJVATyjFHN2Bcrh4cJfAJX5LBCjqHoqNKhvPHpump';
    
    const params = {
        device_id: 'b93aa0d1-a85e-4d5c-be57-c58a5932fce7',
        fp_did: '76c9f7989ab9b34edbced17d43064d5f',
        client_id: 'gmgn_web_20250926-4643-32dc122',
        from_app: 'gmgn',
        app_ver: '20250926-4643-32dc122',
        tz_name: 'Europe/Samara',
        tz_offset: '14400',
        app_lang: 'ru',
        os: 'web',
        limit: '5000',
        maker: ''
    };

    let allTransactions = [];
    let stats = {
        totalSeconds: 0,
        secondsWithTransactions: 0,
        transactionsPerSecond: [],
        startTime: Date.now(),
        totalTransactions: 0,
        candlesCount: to - from + 1, // предполагаем все секунды
        volumeStats: {
            totalVolume: 0,
            volumePerTransaction: 0,
            volumePerSecond: 0,
            volumePerCandle: 0,
            maxVolumePerCandle: 0,
            candlesData: []
        }
    };

    console.log(`Резервный метод: сбор по всем ${stats.candlesCount} секундам...`);

    for (let current = from; current <= to; current++) {
        const urlParams = new URLSearchParams({
            ...params,
            from: current.toString(),
            to: current.toString()
        });

        const url = `${baseUrl}?${urlParams.toString()}`;
        
        try {
            const response = await fetch(url);
            const data = await response.json();
            
            let transactionsThisSecond = 0;
            let volumeThisSecond = 0;
            
            if (data.code === 0 && data.data && data.data.history) {
                const newTransactions = data.data.history.filter(
                    t => !allTransactions.some(existing => existing.id === t.id)
                );
                transactionsThisSecond = newTransactions.length;
                
                // Считаем объем для новых транзакций
                volumeThisSecond = newTransactions.reduce((sum, transaction) => {
                    return sum + parseFloat(transaction.amount_usd || 0);
                }, 0);
                
                allTransactions.push(...newTransactions);
                
                stats.totalSeconds++;
                stats.totalTransactions = allTransactions.length;
                stats.volumeStats.totalVolume += volumeThisSecond;
                
                if (transactionsThisSecond > 0) {
                    stats.secondsWithTransactions++;
                    stats.transactionsPerSecond.push({
                        second: current,
                        count: transactionsThisSecond,
                        volume: volumeThisSecond
                    });
                }
                
                console.log(`Секунда ${current}: ${transactionsThisSecond} транз/сек, объем: $${volumeThisSecond.toFixed(2)} | Всего: ${allTransactions.length} транзакций`);
            } else {
                console.log(`Секунда ${current}: 0 транз/сек | Всего: ${allTransactions.length} транзакций`);
                stats.totalSeconds++;
            }
            
            await new Promise(resolve => setTimeout(resolve, 1000));
        } catch (error) {
            console.error(`Ошибка на секунде ${current}:`, error);
            stats.totalSeconds++;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }

    return generateFinalReport(allTransactions, stats);
}

// Генерация финального отчета
function generateFinalReport(allTransactions, stats) {
    const totalTime = Date.now() - stats.startTime;
    
    // Расчет статистики по транзакциям
    const averageTPS = stats.totalTransactions / stats.candlesCount;
    const averageTPSActive = stats.secondsWithTransactions > 0 
        ? stats.totalTransactions / stats.secondsWithTransactions 
        : 0;
    
    const maxTPS = stats.transactionsPerSecond.length > 0 
        ? Math.max(...stats.transactionsPerSecond.map(t => t.count))
        : 0;
    
    const minTPS = stats.transactionsPerSecond.length > 0 
        ? Math.min(...stats.transactionsPerSecond.map(t => t.count))
        : 0;

    // Расчет статистики по объему
    const volumeStats = calculateVolumeStats(allTransactions, stats);

    console.log('\n========================================');
    console.log('Сбор завершен!');
    console.log('========================================');
    console.log('ОБЩАЯ СТАТИСТИКА:');
    console.log(`Всего транзакций: ${stats.totalTransactions}`);
    console.log(`Уникальных холдеров: ${new Set(allTransactions.map(t => t.maker)).size}`);
    console.log(`Общее время сбора: ${(totalTime / 1000).toFixed(1)} сек`);
    console.log(`Обработано секунд: ${stats.candlesCount}`);
    console.log(`Секунд с транзакциями: ${stats.secondsWithTransactions}`);
    console.log(`Секунд без транзакций: ${stats.candlesCount - stats.secondsWithTransactions}`);
    
    console.log('\nСТАТИСТИКА ПО ОБЪЕМУ:');
    console.log(`Общий объем: $${volumeStats.totalVolume.toFixed(2)}`);
    console.log(`Средний объем на 1 транзакцию: $${volumeStats.volumePerTransaction.toFixed(2)}`);
    console.log(`Средний объем на 1 секунду: $${volumeStats.volumePerSecond.toFixed(2)}`);
    console.log(`Средний объем на 1 свечу: $${volumeStats.volumePerCandle.toFixed(2)}`);
    console.log(`Максимальный объем на 1 свечу: $${volumeStats.maxVolumePerCandle.toFixed(2)}`);
    
    console.log('\nСКОРОСТЬ ТРАНЗАКЦИЙ:');
    console.log(`Средняя скорость: ${averageTPS.toFixed(2)} транз/сек`);
    console.log(`Средняя скорость (только секунды с транзакциями): ${averageTPSActive.toFixed(2)} транз/сек`);
    console.log(`Максимальная скорость: ${maxTPS} транз/сек`);
    console.log(`Минимальная скорость: ${minTPS} транз/сек`);
    console.log(`Общая скорость сбора: ${(stats.totalTransactions / (totalTime / 1000)).toFixed(2)} транз/сек`);
    
    const buyCount = allTransactions.filter(t => t.event === 'buy').length;
    const sellCount = allTransactions.filter(t => t.event === 'sell').length;
    const buyVolume = allTransactions.filter(t => t.event === 'buy').reduce((sum, t) => sum + parseFloat(t.amount_usd || 0), 0);
    const sellVolume = allTransactions.filter(t => t.event === 'sell').reduce((sum, t) => sum + parseFloat(t.amount_usd || 0), 0);
    
    console.log('\nТИПЫ ТРАНЗАКЦИЙ:');
    console.log(`Покупок (buy): ${buyCount} (${((buyCount / stats.totalTransactions) * 100).toFixed(1)}%), объем: $${buyVolume.toFixed(2)}`);
    console.log(`Продаж (sell): ${sellCount} (${((sellCount / stats.totalTransactions) * 100).toFixed(1)}%), объем: $${sellVolume.toFixed(2)}`);
    
    if (stats.transactionsPerSecond.length > 0) {
        const topSeconds = [...stats.transactionsPerSecond]
            .sort((a, b) => b.volume - a.volume)
            .slice(0, 5);
        
        console.log('\nТОП-5 СЕКУНД ПО ОБЪЕМУ:');
        topSeconds.forEach((sec, index) => {
            console.log(`${index + 1}. Секунда ${sec.second}: $${sec.volume.toFixed(2)} (${sec.count} транзакций)`);
        });
    }
    
    return {
        transactions: allTransactions,
        statistics: {
            totalTransactions: stats.totalTransactions,
            uniqueHolders: new Set(allTransactions.map(t => t.maker)).size,
            averageTPS: averageTPS,
            averageTPSActive: averageTPSActive,
            maxTPS: maxTPS,
            minTPS: minTPS,
            totalTime: totalTime,
            candlesCount: stats.candlesCount,
            secondsWithTransactions: stats.secondsWithTransactions,
            buyCount: buyCount,
            sellCount: sellCount,
            volumeStats: volumeStats
        }
    };
}

// Расчет статистики по объему
function calculateVolumeStats(allTransactions, stats) {
    // Общий объем из всех транзакций
    const totalVolume = allTransactions.reduce((sum, transaction) => {
        return sum + parseFloat(transaction.amount_usd || 0);
    }, 0);
    
    // Средний объем на транзакцию
    const volumePerTransaction = stats.totalTransactions > 0 ? totalVolume / stats.totalTransactions : 0;
    
    // Средний объем на секунду
    const volumePerSecond = stats.candlesCount > 0 ? totalVolume / stats.candlesCount : 0;
    
    // Статистика по свечам
    let volumePerCandle = 0;
    let maxVolumePerCandle = 0;
    
    if (stats.volumeStats.candlesData.length > 0) {
        // Используем данные из свечей
        const totalCandleVolume = stats.volumeStats.candlesData.reduce((sum, candle) => {
            return sum + parseFloat(candle.volume || 0);
        }, 0);
        
        volumePerCandle = totalCandleVolume / stats.volumeStats.candlesData.length;
        maxVolumePerCandle = Math.max(...stats.volumeStats.candlesData.map(candle => parseFloat(candle.volume || 0)));
    } else {
        // Используем данные из транзакций (резервный метод)
        volumePerCandle = volumePerSecond; // для резервного метода свечи = секунды
        maxVolumePerCandle = stats.transactionsPerSecond.length > 0 
            ? Math.max(...stats.transactionsPerSecond.map(t => t.volume))
            : 0;
    }
    
    return {
        totalVolume: totalVolume,
        volumePerTransaction: volumePerTransaction,
        volumePerSecond: volumePerSecond,
        volumePerCandle: volumePerCandle,
        maxVolumePerCandle: maxVolumePerCandle
    };
}

// Запуск
collectTransactions().then(result => {
    console.log('\nДанные готовы для использования!');
    // result.transactions - массив всех транзакций
    // result.statistics - объект со статистикой
});