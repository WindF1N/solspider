(function() {
    console.log("Token age filter script loaded.");

    // Объект для хранения токенов и счетчиков проверок
    const tokenChecks = new Map();
    
    // Настройки Telegram
    const TELEGRAM_BOT_TOKEN = '7462651009:AAEU8ubMvkWP62vUOncvpYXSU-D04JeHq-E';
    const TELEGRAM_CHAT_ID = '-1002936713835';
    
    // Функция для извлечения адреса контракта из ссылки
    const extractContractAddress = (url) => {
        try {
            const match = url.match(/\/sol\/token\/([a-zA-Z0-9]+)/);
            return match ? match[1] : 'N/A';
        } catch (error) {
            return 'N/A';
        }
    };

    // Функция для отправки сообщения в Telegram
    const sendToTelegram = async (tokenData) => {
    const contractAddress = extractContractAddress(tokenData.link);
    
    const message = `<b>🚨 ТОКЕН ОБНАРУЖЕН 🚨</b>

<b>📊 Основная информация:</b>
• <b>Название:</b> ${tokenData.name}
• <b>Позиция в списке:</b> ${tokenData.position}
• <b>Контракт:</b> <code>${contractAddress}</code>
• <b>Возраст:</b> ${tokenData.age}
• <b>Dev Age:</b> ${tokenData.devAge}

<b>💰 Финансовые показатели:</b>
• <b>Market Cap:</b> ${tokenData.mcap}
• <b>Объем (5m):</b> ${tokenData.volume}
• <b>Транзакции (5m):</b> ${tokenData.tx}
• <b>Комиссии:</b> ${tokenData.fees}

<b>👥 Держатели:</b>
• <b>Всего держателей:</b> ${tokenData.holders}
• <b>Топ 10:</b> ${tokenData.top10}
• <b>Инсайдеры:</b> ${tokenData.insider}
• <b>Бандлеры:</b> ${tokenData.bundler}

<b>⚠️ Безопасность:</b>
• <b>Фишинг:</b> ${tokenData.phishing}
• <b>Снайперы:</b> ${tokenData.sniper}

<b>👨‍💻 Разработчик:</b>
• <b>Инфо:</b> ${tokenData.devInfo}
• <b>KOLs:</b> ${tokenData.kols}

<b>📈 Активность:</b>
• <b>Покупатели (Axiom):</b> ${tokenData.buyers}

<b>🔍 Проверки:</b> ${tokenData.checks}

<b>🕒 Время отправки:</b> ${new Date().toLocaleString('ru-RU', { 
    year: 'numeric', 
    month: '2-digit', 
    day: '2-digit', 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit' 
})}

${tokenData.link}`;

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
                parse_mode: 'HTML',
                disable_web_page_preview: true,
                reply_markup: {
                    inline_keyboard: [
                        [
                            {
                                text: 'QUICK BUY',
                                url: `https://t.me/alpha_web3_bot?start=call-dex_men-SO-${contractAddress}`
                            }
                        ]
                    ]
                }
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
        const tableBody = document.querySelector('.flex.flex-col.flex-1.overflow-y-auto.overflow-x-hidden.border-line-100.bg-bg-100:first-child .g-table-body:first-child');
        if (!tableBody) return -1;
        
        const allTokens = document.querySelectorAll('.flex.flex-col.flex-1.overflow-y-auto.overflow-x-hidden.border-line-100.bg-bg-100:first-child .g-table-body:first-child > div > div');
        return Array.from(allTokens).indexOf(element) + 1;
    };

    // Функция для получения текста из элемента с обработкой ошибок
    const getElementText = (element, selector, fallback = "-") => {
        try {
            const foundElement = element.querySelector(selector);
            if (!foundElement) return fallback;
            
            // Для элементов с детьми берем текст последнего ребенка
            if (foundElement.children && foundElement.children.length == 2) {
                return foundElement.children[1].innerText.trim() || fallback;
            }

	    if (selector.includes("path")) {
		if (foundElement.parentElement.parentElement.children && foundElement.parentElement.parentElement.children.length >= 2) {
		     if (selector.includes('path[d="M3.30859 11.3997C3.30859 11.0131 3.62199 10.6997 4.00859 10.6997H11.9929C12.3795 10.6997 12.6929 11.0131 12.6929 11.3997C12.6929 11.7863 12.3795 12.0997 11.9929 12.0997H4.00859C3.62199 12.0997 3.30859 11.7863 3.30859 11.3997Z"]')) {
			if (foundElement.parentElement.parentElement.children.length > 1) {
				return foundElement.parentElement.parentElement.children[foundElement.parentElement.parentElement.children.length - 1].innerText.trim();
			} else {
				return foundElement.parentElement.parentElement.innerText.trim();
			}

		     } else {
			return foundElement.parentElement.parentElement.children[1].innerText.trim();
		     }
		}
		if (foundElement.parentElement.parentElement.tagName === 'A') {
		     return foundElement.parentElement.parentElement.parentElement.innerText.trim();
		}
	    	return foundElement.parentElement.parentElement.innerText.trim();
	    }  
            
            return foundElement.innerText.trim() || fallback;
        } catch (error) {
            return fallback;
        }
    };

    const filterAndLogTokens = () => {
        const tokenElements = document.querySelectorAll('.flex.flex-col.flex-1.overflow-y-auto.overflow-x-hidden.border-line-100.bg-bg-100:first-child .g-table-body:first-child > div > div');

        tokenElements.forEach(element => {
            const position = getTokenPosition(element);
            
            // Проверяем только токены на позиции 1 и ниже
            if (position < 1) {
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

                // Extract token details
                const tokenNameElement = element.querySelector('.whitespace-nowrap.font-medium');
                const tokenName = tokenNameElement ? tokenNameElement.innerText.trim() : 'N/A';

                const tokenLinkElement = element.querySelector('a[href*="/sol/token/"]');
                const tokenLink = tokenLinkElement ? tokenLinkElement.href : 'N/A';

                // Получаем все данные о токене
                const tokenDevAge = getElementText(element, 'path[d="M3.30859 11.3997C3.30859 11.0131 3.62199 10.6997 4.00859 10.6997H11.9929C12.3795 10.6997 12.6929 11.0131 12.6929 11.3997C12.6929 11.7863 12.3795 12.0997 11.9929 12.0997H4.00859C3.62199 12.0997 3.30859 11.7863 3.30859 11.3997Z"]');
                const tokenTop10Pcnt = getElementText(element, 'path[d="M8.44046 9.17151C8.82702 9.17155 9.14065 9.48513 9.14065 9.8717 9.14065 10.2583 8.82702 10.5719 8.44046 10.5719H4.95999C3.50234 10.5721 2.24598 11.5971 1.95315 13.025L1.86721 13.4449C1.78006 13.87 2.10426 14.2681 2.53811 14.2682H8.44046C8.82699 14.2682 9.1406 14.5819 9.14065 14.9684 9.14065 15.355 8.82702 15.6685 8.44046 15.6686H2.53811C1.21802 15.6684.229981 14.4569.495143 13.1637L.58108 12.7438C1.00741 10.6645 2.83751 9.17168 4.95999 9.17151H8.44046ZM10.2675 3.93066C10.2675 2.67914 9.25331 1.66431 8.00186 1.66406 6.75019 1.66406 5.73526 2.67899 5.73526 3.93066 5.7355 5.18213 6.75034 6.19629 8.00186 6.19629 9.25316 6.19604 10.2672 5.18198 10.2675 3.93066ZM11.6679 3.93066C11.6676 5.95517 10.0264 7.59643 8.00186 7.59668 5.97714 7.59668 4.33511 5.95533 4.33486 3.93066 4.33486 1.9058 5.97699.263672 8.00186.263672 10.0265.263918 11.6679 1.90595 11.6679 3.93066Z"]');
                const tokenInsiderPcnt = getElementText(element, 'path[d="M.689614 12.1594C.689614 11.0835 1.08748 10.4494 1.41618 9.9514 1.72553 9.48274 1.91123 9.20941 1.91129 8.69261 1.91129 8.14089 1.7646 7.87098 1.64274 7.7307 1.5115 7.57983 1.33283 7.49205 1.13102 7.43285.760145 7.32396.547595 6.93462.656411 6.56371.7653 6.19283 1.15463 5.98028 1.52555 6.0891 1.8594 6.18705 2.32231 6.37938 2.6984 6.81175 3.08385 7.25489 3.31071 7.65905 3.31071 8.47916 3.31063 9.46081 2.88521 10.2668 2.58415 10.7229 2.30239 11.1498 2.09 11.5001 2.09 12.1594 2.09003 12.7991 2.35162 13.2541 2.78629 13.5715 3.24485 13.9063 3.93811 14.1135 4.79606 14.1135H7.61247C7.99907 14.1135 8.31266 14.4271 8.31266 14.8137 8.31251 15.2002 7.99897 15.5139 7.61247 15.5139H4.79606C3.73645 15.5139 2.72612 15.2608 1.9611 14.7024 1.17234 14.1266.689637 13.2549.689614 12.1594ZM9.6165 6.44504C9.6165 6.90708 9.24193 7.28165 8.77989 7.28165 8.31784 7.28165 7.94328 6.90708 7.94328 6.44504 7.94328 5.98299 8.31784 5.60843 8.77989 5.60843 9.24193 5.60843 9.6165 5.98299 9.6165 6.44504Z"]');
                const tokenBundlerPcnt = getElementText(element, 'path[d="M14.8795 8.01054C15.0726 8.3411 14.951 8.75958 14.608 8.94575L8.39997 12.3159C8.1518 12.4506 7.84797 12.4506 7.59979 12.3159L1.39171 8.94575C1.04875 8.75958 0.927206 8.3411 1.1203 8.01054C1.31345 7.68 1.74766 7.56288 2.09064 7.74895L7.99988 10.9558L13.9091 7.74895C14.2521 7.56288 14.6863 7.68 14.8795 8.01054Z"]');
                const tokenPhishingPcnt = getElementText(element, 'path[d="M15.9089 5.41589V2.6366C15.9089 1.69772 15.1476 0.936407 14.2087 0.936401H9.8806C7.28486 0.936397 5.18041 3.04086 5.18041 5.6366V10.1971H0.859117C0.148311 10.1971 -0.209349 11.0553 0.290758 11.5604L3.5017 14.8036C4.63305 15.9458 6.58079 15.1448 6.5808 13.537V11.6005L9.67845 11.6161C13.1142 11.6327 15.9089 8.85173 15.9089 5.41589ZM5.18041 13.537C5.1804 13.8943 4.74724 14.0722 4.49584 13.8182L2.29759 11.5975H5.18041V13.537ZM14.5085 5.41589C14.5085 8.07589 12.3453 10.2285 9.68529 10.2157L6.5808 10.2001V5.6366C6.5808 3.81406 8.05806 2.33679 9.8806 2.33679H14.2087C14.3744 2.3368 14.5085 2.47092 14.5085 2.6366V5.41589Z"]');
                const tokenSniperPcnt = getElementText(element, 'path[d="M13.4293 8.43193C13.4293 5.70935 11.2228 3.50298 8.50022 3.50289C5.77759 3.50289 3.57119 5.70929 3.57119 8.43193C3.57128 11.1545 5.77764 13.361 8.50022 13.361C11.2227 13.3609 13.4292 11.1544 13.4293 8.43193ZM14.898 8.43193C14.8979 11.9659 12.0342 14.8296 8.50022 14.8297C4.96613 14.8297 2.10149 11.966 2.10139 8.43193C2.10139 4.89777 4.96607 2.0331 8.50022 2.0331C12.0343 2.03319 14.898 4.89783 14.898 8.43193Z"]');
                const tokenHolders = getElementText(element, 'path[d="M8.31084 3.9917C8.31084 2.87196 7.40323 1.96438 6.2835 1.96436 5.16375 1.96436 4.25616 2.87195 4.25616 3.9917 4.25618 5.11143 5.16376 6.01904 6.2835 6.01904 7.40322 6.01902 8.31082 5.11141 8.31084 3.9917ZM9.71124 3.9917C9.71121 5.88461 8.17641 7.41941 6.2835 7.41943 4.39056 7.41943 2.85579 5.88463 2.85577 3.9917 2.85577 2.09875 4.39055.563965 6.2835.563965 8.17643.563991 9.71124 2.09877 9.71124 3.9917ZM12.1598 4.01685C12.1598 3.22552 11.9049 2.64414 11.4987 2.07056 11.2754 1.75508 11.3503 1.31836 11.6657 1.09497 11.9812.871706 12.4179.946537 12.6413 1.26196 13.1666 2.00384 13.5602 2.86209 13.5602 4.01685 13.5601 5.17861 13.0665 6.18755 12.6364 6.77856 12.4089 7.09112 11.9704 7.16038 11.6579 6.93286 11.3453 6.70534 11.2761 6.2669 11.5036 5.95435 11.8149 5.52661 12.1597 4.80068 12.1598 4.01685ZM10.7231 11.3625C10.7231 10.3684 9.91648 9.56274 8.92236 9.56274H3.64404C2.64997 9.56278 1.84426 10.3685 1.84424 11.3625V13.6692H10.7231V11.3625ZM12.1226 14.3684C12.1226 14.755 11.809 15.0686 11.4224 15.0686H1.14404C.958389 15.0686.780202 14.9948.648926 14.8635.550601 14.7651.484391 14.6405.45752 14.5061L.443848 14.3684V11.3625C.443885 9.59529 1.87679 8.16239 3.64404 8.16235H8.92236C10.6897 8.16235 12.1226 9.59524 12.1226 11.3625V14.3684ZM14.3776 14.3691V11.9736C14.3776 11.31 14.2245 10.6549 13.9294 10.0605L13.5641 9.32617C13.3922 8.97996 13.5334 8.5597 13.8796 8.3877 14.2258 8.21574 14.646 8.35696 14.818 8.70312L15.1833 9.4375C15.5746 10.2254 15.778 11.0939 15.778 11.9736V14.3691C15.7779 14.7556 15.4643 15.0693 15.0778 15.0693 14.6913 15.0693 14.3777 14.7556 14.3776 14.3691Z"]');
                const tokenBuyerCountFromAxiom = getElementText(element, 'path[d="M13.1875 4.03802C13.1875 3.87233 13.0524 3.73821 12.8867 3.73821H3.11133C2.94564 3.73821 2.81152 3.87233 2.81152 4.03802V13.3068C2.81152 13.4725 2.94564 13.6066 3.11133 13.6066H12.8867C13.0524 13.6066 13.1875 13.4725 13.1875 13.3068V4.03802ZM14.5869 13.3068C14.5869 14.2457 13.8256 15.007 12.8867 15.007H3.11133C2.17245 15.007 1.41113 14.2457 1.41113 13.3068V4.03802C1.41113 3.09913 2.17244 2.33782 3.11133 2.33782H12.8867C13.8256 2.33782 14.5869 3.09913 14.5869 4.03802V13.3068Z"]');
                const tokenDevInfo = getElementText(element, 'path[d="M7.43491 1.00342C7.77213 0.632075 8.38006 0.658537 8.67905 1.08252L11.2689 4.75635L14.8353 3.4126L14.9398 3.38037C15.4642 3.25876 15.9741 3.69302 15.9125 4.24951L14.9076 13.3228C14.8121 14.1838 14.0845 14.8354 13.2181 14.8354H2.87437C2.01401 14.8354 1.28962 14.1926 1.18687 13.3384L0.094093 4.25635C0.0226607 3.66184 0.606133 3.20222 1.16734 3.41064L4.78648 4.75732L7.37144 1.0835L7.43491 1.00342ZM5.66538 5.94189C5.4562 6.23931 5.07257 6.35877 4.73179 6.23193L1.60191 5.06592L2.57651 13.1714C2.59472 13.322 2.7226 13.4351 2.87437 13.4351H13.2181C13.371 13.435 13.4991 13.3204 13.516 13.1685L14.4125 5.06689L11.3285 6.22998C10.9875 6.35837 10.603 6.24049 10.3929 5.94287L8.02573 2.58447L5.66538 5.94189Z"]');
                const tokenKOLs = getElementText(element, 'path[d="M12.5798 7.46814V3.02087C12.5798 2.85522 12.4457 2.7211 12.28 2.72107H3.71948C3.55384 2.72112 3.41968 2.85522 3.41968 3.02087V7.46912C3.41977 7.87651 3.61125 8.26058 3.93628 8.50623L7.9978 11.5756L12.0632 8.50623C12.3886 8.26055 12.5798 7.87582 12.5798 7.46814ZM13.9802 7.46814C13.9802 8.31486 13.5827 9.11316 12.907 9.62341L8.698 12.8011V13.9857H11.1472C11.5337 13.9857 11.8472 14.2985 11.8474 14.6849C11.8474 15.0715 11.5338 15.3851 11.1472 15.3851H4.83569C4.44909 15.3851 4.1355 15.0715 4.1355 14.6849C4.1357 14.2985 4.44922 13.9857 4.83569 13.9857H7.29761V12.8011L3.09155 9.62244C2.41661 9.11219 2.01938 8.31523 2.01929 7.46912V3.02087C2.01929 2.08203 2.78063 1.32073 3.71948 1.32068H12.28C13.2188 1.32071 13.9801 2.08208 13.9802 3.02087V7.46814Z"]');
                const tokenMarketCap = getElementText(element, 'div.flex.z-10.flex-col.w-0.items-end.absolute.right-0 > div:nth-child(1) > div:nth-child(2)');
                const tokenVolume = getElementText(element, 'div.flex.z-10.flex-col.w-0.items-end.absolute.right-0 > div:nth-child(1) > div:nth-child(1)');
		const tokenFees = getElementText(element, 'div.flex.z-10.flex-col.w-0.items-end.absolute.right-0 > div:nth-child(2) > div:nth-child(1) > span:last-child');
                const tokenTX = getElementText(element, 'div.flex.z-10.flex-col.w-0.items-end.absolute.right-0 > div:nth-child(2) > div:nth-child(2) > span:nth-child(2)');

                // Получаем уникальный ID токена
                const tokenId = getTokenId(element);
                
                if (!tokenId) return;

                if (tokenFees == "0") return;

                // Проверяем, содержит ли devAge процент или DevSell
                const hasPercentage = tokenDevAge ? (tokenDevAge.includes('%') || tokenDevAge.includes('DS')) : false;

                if (hasPercentage && tokenDevInfo.includes('/1') && tokenDevAge !== '0%') {
                    // Если токен уже в процессе проверки
                    if (tokenChecks.has(tokenId)) {
                        const checkData = tokenChecks.get(tokenId);
                        checkData.checkCount++;
                        checkData.lastSeen = Date.now();
                        checkData.currentPosition = position;
                        
                        // Если достигли 20 проверок - отправляем в Telegram
                        if (checkData.checkCount >= 20 && !checkData.sentToTelegram) {
                            const tokenData = {
                                name: tokenName,
                                age: ageString,
                                devAge: tokenDevAge,
                                devInfo: tokenDevInfo,
                                link: tokenLink,
                                checks: checkData.checkCount,
                                position: position,
                                fees: tokenFees,
                                top10: tokenTop10Pcnt,
                                insider: tokenInsiderPcnt,
                                bundler: tokenBundlerPcnt,
                                phishing: tokenPhishingPcnt,
                                sniper: tokenSniperPcnt,
                                holders: tokenHolders,
                                kols: tokenKOLs,
                                mcap: tokenMarketCap,
                                volume: tokenVolume,
                                tx: tokenTX,
                                buyers: tokenBuyerCountFromAxiom
                            };
                            
                            console.log("[Token Detected]", tokenData);
                            
                            // Отправляем в Telegram
                            sendToTelegram(tokenData);
                            
                            // Помечаем токен как отправленный
                            checkData.sentToTelegram = true;
                            checkData.processed = true;
                        }
                    } else {
                        // Первое обнаружение токена
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
        
        if (tokenChecks.size > 0) {
            console.log(`Active tokens in check: ${tokenChecks.size}`);
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