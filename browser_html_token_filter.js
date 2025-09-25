(function() {
    console.log("Token age filter script loaded.");

    // Объект для хранения токенов и счетчиков проверок
    const tokenChecks = new Map();
    
    // Настройки Telegram
    const TELEGRAM_BOT_TOKEN = '7462651009:AAEU8ubMvkWP62vUOncvpYXSU-D04JeHq-E';
    const TELEGRAM_CHAT_ID = '-1002782703266';
    
    // Функция для отправки сообщения в Telegram
    const sendToTelegram = async (tokenData) => {
        const message = `${tokenData.name}\n\n` +
                       `🔗 ${tokenData.link}`;

        const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    chat_id: TELEGRAM_CHAT_ID,
                    text: message,
                    disable_web_page_preview: false
                })
            });
            
            const result = await response.json();
            if (result.ok) {
                console.log('✅ Сообщение отправлено в Telegram');
            } else {
                console.error('❌ Ошибка отправки в Telegram:', result);
            }
        } catch (error) {
            console.error('❌ Ошибка при отправке в Telegram:', error);
        }
    };

    // Функция для проверки, что все буквы в строке заглавные
    const isUpperCase = (str) => {
        return str === str.toUpperCase() && str.toLowerCase() !== str.toUpperCase();
    };

    // Функция для получения уникального идентификатора токена
    const getTokenId = (element) => {
        const tokenLinkElement = element.querySelector('a[href*="/sol/token/"]');
        return tokenLinkElement ? tokenLinkElement.href : null;
    };

    // Функция для получения позиции токена в таблице
    const getTokenPosition = (element) => {
        const tableBody = document.querySelector('.g-table-body:first-child');
        if (!tableBody) return -1;
        
        const allTokens = document.querySelectorAll('.g-table-body:first-child > div > div');
        return Array.from(allTokens).indexOf(element) + 1; // +1 для человекочитаемой позиции
    };

    const filterAndLogTokens = () => {
        const tokenElements = document.querySelectorAll('.g-table-body:first-child > div > div');

        tokenElements.forEach(element => {
            const position = getTokenPosition(element);
            
            // Проверяем только токены на позиции 10 и ниже
            if (position < 3) {
                // Если токен в топ-4, удаляем его из проверки если он там есть
                const tokenId = getTokenId(element);
                if (tokenId && tokenChecks.has(tokenId) && !tokenChecks.get(tokenId).processed) {
                    tokenChecks.delete(tokenId);
                    console.log(`Token removed from checks (position ${position}): ${tokenId}`);
                }
                return;
            }

            const ageElement = element.querySelector('.text-green-50.font-medium');
            if (ageElement) {
                const ageString = ageElement.innerText.trim();

                // Extract other token details
                const tokenNameElement = element.querySelector('.whitespace-nowrap.font-medium');
                const tokenName = tokenNameElement ? tokenNameElement.innerText.trim() : 'N/A';

                const tokenLinkElement = element.querySelector('a[href*="/sol/token/"]');
                const tokenLink = tokenLinkElement ? tokenLinkElement.href : 'N/A';

                const tokenDevAgeElement = element.querySelector('path[d="M3.30859 11.3997C3.30859 11.0131 3.62199 10.6997 4.00859 10.6997H11.9929C12.3795 10.6997 12.6929 11.0131 12.6929 11.3997C12.6929 11.7863 12.3795 12.0997 11.9929 12.0997H4.00859C3.62199 12.0997 3.30859 11.7863 3.30859 11.3997Z"]').parentElement.parentElement;
                const tokenDevAge = tokenDevAgeElement ? tokenDevAgeElement.children[tokenDevAgeElement.children.length - 1].innerText : "N/A";

                const tokenFeesElement = element.querySelector('path[d="M2.65639 9.70688C2.73558 9.62768 2.84448 9.58148 2.95998 9.58148H13.4338C13.6252 9.58148 13.7209 9.81247 13.5856 9.94777L11.5166 12.0168C11.4374 12.096 11.3285 12.1422 11.213 12.1422H0.739159C0.547766 12.1422 0.45207 11.9112 0.587365 11.7759L2.65639 9.70688Z"]').parentElement.parentElement;
                const tokenFees = tokenFeesElement ? tokenFeesElement.children[tokenFeesElement.children.length - 1].innerText : "0";

                // Получаем уникальный ID токена
                const tokenId = getTokenId(element);
                
                if (!tokenId) return;

                if (tokenFees == "0") return;

                // Проверяем, содержит ли devAge процент или DevSell
                const hasPercentage = tokenDevAge ? tokenDevAge.includes('%') : true;
                const hasDevSell = tokenDevAge ? tokenDevAge.includes('DS') : true;

                if (hasPercentage || hasDevSell) {
                    // Если токен уже в процессе проверки
                    if (tokenChecks.has(tokenId)) {
                        const checkData = tokenChecks.get(tokenId);
                        checkData.checkCount++;
                        checkData.lastSeen = Date.now();
                        checkData.currentPosition = position; // Обновляем позицию
                        
                        // Если достигли 1 проверок - выводим токен
                        if (checkData.checkCount >= 3 && !checkData.sentToTelegram) {
                            const tokenData = {
                                name: tokenName,
                                age: ageString,
                                devAge: tokenDevAge,
                                link: tokenLink,
                                checks: checkData.checkCount,
                                position: position
                            };
                            
                            console.log("[New Token (<1 day)]", tokenData);
                            
                            // Отправляем в Telegram
                            sendToTelegram(tokenData);
                            
                            // Помечаем токен как отправленный
                            checkData.sentToTelegram = true;
                            checkData.processed = true;
                        }
                    } else {
                        // Первое обнаружение токена (только если позиция >= 5)
                        tokenChecks.set(tokenId, {
                            checkCount: 1,
                            lastSeen: Date.now(),
                            processed: false,
                            sentToTelegram: false,
                            name: tokenName,
                            currentPosition: position
                        });
                        console.log(`New token added to checks (position ${position}): ${tokenName}`);
                    }
                    
                    // Добавляем проверку на заглавные буквы
                    if (!isUpperCase(tokenName)) {
                        console.log(`Token "${tokenName}" removed from checks (not all uppercase): ${tokenName}`);
                        tokenChecks.delete(tokenId);
                        return;
                    }

                } else {
                    // Если процента нет, удаляем токен из проверки
                    if (tokenChecks.has(tokenId) && !tokenChecks.get(tokenId).processed) {
                        tokenChecks.delete(tokenId);
                        console.log(`Token removed from checks (no %/DS): ${tokenName}`);
                    }
                }
            }
        });
    };

    // Функция для очистки старых записей
    const cleanupOldTokens = () => {
        const now = Date.now();
        const tenMinutesAgo = now - 10 * 60 * 1000;
        
        for (const [tokenId, checkData] of tokenChecks.entries()) {
            // Удаляем записи старше 10 минут, которые не были обработаны
            if (!checkData.processed && checkData.lastSeen < tenMinutesAgo) {
                tokenChecks.delete(tokenId);
                console.log(`Removed old token from checks: ${checkData.name}`);
            }
        }
    };

    // Запускаем фильтр сразу
    filterAndLogTokens();

    // Запускаем периодическую проверку
    const checkInterval = setInterval(() => {
        filterAndLogTokens();
        cleanupOldTokens();
        
        // Логируем статистику (опционально)
        if (tokenChecks.size > 0) {
            console.log(`Active tokens in check: ${tokenChecks.size}`);
            // Можно добавить логирование позиций для отладки
            tokenChecks.forEach((data, tokenId) => {
                if (!data.processed) {
                    console.log(`Token "${data.name}" at position ${data.currentPosition}, checks: ${data.checkCount}`);
                }
            });
        }
    }, 1000);

    // Функция для отладки - просмотр текущих проверок
    window.showTokenChecks = () => {
        console.log("Current token checks:", Array.from(tokenChecks.entries()));
    };

    // Функция для остановки скрипта
    window.stopTokenFilter = () => {
        clearInterval(checkInterval);
        tokenChecks.clear();
        console.log("Token age filter stopped");
    };

    console.log("Token age filter is running. Checking only tokens at position 5 and below.");
})();