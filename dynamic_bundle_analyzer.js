async function fetchBundlerData(isInitialRun) {
    const url = 'https://gmgn.ai/api/v1/rank/sol/swaps/24h?device_id=eeb8dafa-3383-469c-9eff-0d8e7f91772b&fp_did=d77855ac6b24fee27da1ac79e7aaf072&client_id=gmgn_web_20251003-4897-8c49996&from_app=gmgn&app_ver=20251003-4897-8c49996&tz_name=Europe%2FMoscow&tz_offset=10800&app_lang=ru&os=web&orderby=creation_timestamp&direction=desc&filters[]=is_out_market&platforms[]=Pump.fun';

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (data.code === 0 && data.data && data.data.rank.length > 0) {
            let tokensToProcess = data.data.rank;
            if (!isInitialRun) {
                const oneHourAgo = Math.floor(Date.now() / 1000) - (1 * 60 * 60); // Changed to 1 hour
                tokensToProcess = data.data.rank.filter(token => token.creation_timestamp >= oneHourAgo);
                console.log(`Filtered to ${tokensToProcess.length} tokens created in the last 1 hour.`);
            }

            const loadedEligibleBundlers = await getDataFromIndexedDB(STORE_ELIGIBLE_BUNDLERS);
            const loadedMakerPurchases = await getDataFromIndexedDB(STORE_MAKER_PURCHASES);
            const loadedTokenInformation = await getDataFromIndexedDB(STORE_TOKEN_INFORMATION);

            let currentEligibleBundlers = loadedEligibleBundlers; // Declared once and initialized with loaded data
            const makerPurchases = loadedMakerPurchases; // Map<makerAddress, Map<tokenAddress, hasAchieved2x>>
            const tokenInformation = loadedTokenInformation; // Map<tokenAddress, { creationTimestamp: number, hasAchieved2x: boolean, lastTransactionCursor: string | null }>
            
            // Collect all unique tokens we need to evaluate (new from rank API + existing from makerPurchases)
            const allTokensToEvaluate = new Set();

            for (const item of tokensToProcess) {
                const tokenAddress = item.address;
                const creationTimestamp = item.creation_timestamp;
                allTokensToEvaluate.add(tokenAddress);
                // Update creation timestamp if newer or not present, initialize lastTransactionCursor
                if (!tokenInformation.has(tokenAddress) || tokenInformation.get(tokenAddress).creationTimestamp < creationTimestamp) {
                    tokenInformation.set(tokenAddress, { creationTimestamp: creationTimestamp, hasAchieved2x: false, lastTransactionCursor: null });
                }
            }

            // Also add tokens from existing makerPurchases that are not in the current rank to re-evaluate if needed
            for (const tokensMap of makerPurchases.values()) {
                for (const tokenAddress of tokensMap.keys()) {
                    if (!tokenInformation.has(tokenAddress)) {
                        console.warn(`Token ${tokenAddress} found in makerPurchases but not in current rank or historical tokenInformation. Skipping 2x check for this token.`);
                    } else {
                        allTokensToEvaluate.add(tokenAddress);
                    }
                }
            }

            for (const tokenAddress of allTokensToEvaluate) {
                const tokenInfo = tokenInformation.get(tokenAddress);
                if (!tokenInfo) continue;

                // Only re-evaluate if not yet achieved 2x or if we have a cursor to continue from
                if (tokenInfo.hasAchieved2x === false || tokenInfo.lastTransactionCursor) {
                    console.log(`\nProcessing Token: ${tokenAddress} (creation: ${tokenInfo.creationTimestamp}) for 2x status`);
                    let nextCursor = tokenInfo.lastTransactionCursor || ''; // Start from last known cursor
                    let transactionsFetched = 0;
                    let allTokenTransactions = []; // To store all transactions for the current token
                    do {
                        let transactionUrl = `https://gmgn.ai/vas/api/v1/token_trades/sol/${tokenAddress}?device_id=eeb8dafa-3383-469c-9eff-0d8e7f91772b&fp_did=d77855ac6b24fee27da1ac79e7aaf072&client_id=gmgn_web_20251001-4892-0e84618&from_app=gmgn&app_ver=20251001-4892-0e84618&tz_name=Europe%2FMoscow&tz_offset=10800&app_lang=ru&os=web&limit=50&maker=&tag=bundler&revert=true`;
                        if (nextCursor) {
                            transactionUrl += `&cursor=${nextCursor}`;
                        }

                        try {
                            const transactionResponse = await fetch(transactionUrl);
                            const transactionData = await transactionResponse.json();

                            if (transactionData.code === 0 && transactionData.data && transactionData.data.history) {
                                transactionData.data.history.forEach(tx => {
                                    if (tx.event === 'buy') {
                                        if (!makerPurchases.has(tx.maker)) {
                                            makerPurchases.set(tx.maker, new Map());
                                        }
                                        makerPurchases.get(tx.maker).set(tokenAddress, false); // Placeholder, updated below
                                    }
                                    allTokenTransactions.push(tx);
                                });
                                transactionsFetched += transactionData.data.history.length;
                                console.log(`Fetched ${transactionData.data.history.length} transactions for ${tokenAddress}. Total: ${transactionsFetched}. Unique buyers so far: ${makerPurchases.size}`);
                                nextCursor = transactionData.data.next || '';
                            } else {
                                console.log(`No transaction history or error for ${tokenAddress} with cursor ${nextCursor}:`, transactionData);
                                nextCursor = ''; // Stop pagination on error or no data
                            }
                        } catch (txError) {
                            console.error(`Error fetching transactions for ${tokenAddress} with cursor ${nextCursor}:`, txError);
                            nextCursor = ''; // Stop pagination on pagination error
                        }
                    } while (nextCursor);

                    // Update the lastTransactionCursor for this token after processing all available transactions for this run
                    tokenInformation.set(tokenAddress, { ...tokenInfo, lastTransactionCursor: nextCursor || null });

                    // Calculate 2x price increase from allTokenTransactions
                    let maxPriceAtCreation = 0;
                    const creationTransactions = allTokenTransactions.filter(tx => tx.timestamp === tokenInfo.creationTimestamp);
                    if (creationTransactions.length > 0) {
                        maxPriceAtCreation = Math.max(...creationTransactions.map(tx => parseFloat(tx.price_usd || 0)));
                    }

                    let hasAchieved2x = false;
                    if (maxPriceAtCreation > 0) {
                        const targetPrice = maxPriceAtCreation * 2;
                        for (const tx of allTokenTransactions) {
                            if (tx.timestamp > tokenInfo.creationTimestamp && parseFloat(tx.price_usd || 0) >= targetPrice) {
                                hasAchieved2x = true;
                                break;
                            }
                        }
                    }
                    tokenInformation.set(tokenAddress, { ...tokenInfo, hasAchieved2x: hasAchieved2x });
                    console.log(`Token ${tokenAddress} achieved 2x price increase: ${hasAchieved2x}`);
                } else {
                    console.log(`Token ${tokenAddress} already achieved 2x price increase, and no new transactions to fetch.`);
                }
            }
            
            // Update makerPurchases with actual 2x status for each token
            for (const [maker, tokensBoughtMap] of makerPurchases.entries()) {
                for (const [token, hasAchieved2xPlaceholder] of tokensBoughtMap.entries()) {
                    if (tokenInformation.has(token)) {
                        tokensBoughtMap.set(token, tokenInformation.get(token).hasAchieved2x);
                    }
                }
            }
            
            // Filter based on new criteria: all tokens bought must achieve 2x, and at least 2 tokens overall
            currentEligibleBundlers.clear(); // Clear for recalculation
            for (const [maker, tokensBoughtMap] of makerPurchases.entries()) {
                let successfulTokensCount = 0;
                let hasNon2xToken = false;

                for (const [token, achieved2x] of tokensBoughtMap.entries()) {
                    if (achieved2x) {
                        successfulTokensCount++;
                    } else {
                        hasNon2xToken = true;
                        break; // Found a token that didn't achieve 2x
                    }
                }

                if (!hasNon2xToken && successfulTokensCount >= 2) {
                    currentEligibleBundlers.add(maker);
                }
            }

            await putDataIntoIndexedDB(STORE_ELIGIBLE_BUNDLERS, currentEligibleBundlers);
            await putDataIntoIndexedDB(STORE_MAKER_PURCHASES, makerPurchases);
            await putDataIntoIndexedDB(STORE_TOKEN_INFORMATION, tokenInformation);

            console.log('\n========================================');
            console.log('Tokens that achieved 2x price increase:');
            console.log('========================================');
            const tokensAchieved2x = [];
            for (const [token, info] of tokenInformation.entries()) {
                if (info.hasAchieved2x) {
                    tokensAchieved2x.push(token);
                }
            }
            if (tokensAchieved2x.length > 0) {
                tokensAchieved2x.forEach(token => console.log(token));
            } else {
                console.log('No tokens achieved 2x price increase.');
            }

            console.log('\n========================================');
            console.log(`Total Eligible Bundler Wallets: ${currentEligibleBundlers.size}`);
            console.log('========================================');
            currentEligibleBundlers.forEach(maker => console.log(maker));

        } else {
            console.log('No data or error in response:', data);
        }
    } catch (error) {
        console.error('Error fetching bundler data:', error);
    }
}

// IndexedDB Constants
const DB_NAME = 'bundlerAnalyzerDB';
const DB_VERSION = 1;
const STORE_ELIGIBLE_BUNDLERS = 'eligibleBundlers';
const STORE_MAKER_PURCHASES = 'makerPurchases';
const STORE_TOKEN_INFORMATION = 'tokenInformation';

// IndexedDB Utility Functions
function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_ELIGIBLE_BUNDLERS)) {
                db.createObjectStore(STORE_ELIGIBLE_BUNDLERS);
            }
            if (!db.objectStoreNames.contains(STORE_MAKER_PURCHASES)) {
                db.createObjectStore(STORE_MAKER_PURCHASES);
            }
            if (!db.objectStoreNames.contains(STORE_TOKEN_INFORMATION)) {
                db.createObjectStore(STORE_TOKEN_INFORMATION);
            }
        };

        request.onsuccess = (event) => {
            resolve(event.target.result);
        };

        request.onerror = (event) => {
            console.error("IndexedDB error:", event.target.errorCode);
            reject(event.target.errorCode);
        };
    });
}

async function putDataIntoIndexedDB(storeName, data) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([storeName], 'readwrite');
        const store = transaction.objectStore(storeName);

        let dataToStore = data;
        if (data instanceof Set) {
            dataToStore = Array.from(data);
        } else if (data instanceof Map) {
            if (storeName === STORE_MAKER_PURCHASES) {
                // For makerPurchases (Map<string, Map<string, boolean>>), convert inner maps to arrays too
                dataToStore = Array.from(data).map(([maker, tokensMap]) => [
                    maker, Array.from(tokensMap)
                ]);
            } else if (storeName === STORE_TOKEN_INFORMATION) {
                // For tokenInformation (Map<string, { creationTimestamp: number, hasAchieved2x: boolean, lastTransactionCursor: string | null }>) 
                dataToStore = Array.from(data).map(([token, info]) => [
                    token, { creationTimestamp: info.creationTimestamp, hasAchieved2x: info.hasAchieved2x, lastTransactionCursor: info.lastTransactionCursor || null }
                ]);
            } else {
                dataToStore = Array.from(data);
            }
        }

        const request = store.put(dataToStore, storeName); // Store under storeName as key

        request.onsuccess = () => {
            resolve();
        };

        request.onerror = (event) => {
            console.error(`Error putting data into ${storeName}:`, event.target.errorCode);
            reject(event.target.errorCode);
        };
    });
}

async function getDataFromIndexedDB(storeName) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([storeName], 'readonly');
        const store = transaction.objectStore(storeName);
        const request = store.get(storeName); // We'll store the whole object under its storeName as key

        request.onsuccess = (event) => {
            let data = event.target.result;
            if (storeName === STORE_ELIGIBLE_BUNDLERS) {
                resolve(data ? new Set(data) : new Set());
            } else if (storeName === STORE_MAKER_PURCHASES) {
                resolve(data ? new Map(data.map(([maker, tokens]) => [maker, new Map(tokens)])) : new Map());
            } else if (storeName === STORE_TOKEN_INFORMATION) {
                resolve(data ? new Map(data.map(([token, info]) => [token, { creationTimestamp: info.creationTimestamp, hasAchieved2x: info.hasAchieved2x, lastTransactionCursor: info.lastTransactionCursor || null }])) : new Map());
            } else {
                resolve(data || null);
            }
        };

        request.onerror = (event) => {
            console.error(`Error getting data from ${storeName}:`, event.target.errorCode);
            reject(event.target.errorCode);
        };
    });
}

// Function to download bundlers to files
async function downloadBundlersAsFiles(bundlers) {
    const bundlerArray = Array.from(bundlers);
    const date = new Date();
    const formattedDate = `0${date.getDate()}`.slice(-2) + '-' + `0${date.getMonth() + 1}`.slice(-2) + '-' + date.getFullYear().toString().slice(-2);

    const fileName = `eligible_bundlers_${formattedDate}.txt`;
    const blob = new Blob([bundlerArray.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Function to trigger manual download of eligible bundlers
async function triggerDownloadOfEligibleBundlers() {
    console.log("Triggering download of eligible bundlers...");
    try {
        const eligibleBundlers = await getDataFromIndexedDB(STORE_ELIGIBLE_BUNDLERS);
        if (eligibleBundlers && eligibleBundlers.size > 0) {
            await downloadBundlersAsFiles(eligibleBundlers); // Call the original function with chunking
            console.log(`Successfully triggered download for ${eligibleBundlers.size} eligible bundlers.`);
        } else {
            console.log("No eligible bundlers found to download.");
        }
    } catch (error) {
        console.error("Error triggering download:", error);
    }
}

// Expose the function globally for manual trigger from console
window.triggerDownloadOfEligibleBundlers = triggerDownloadOfEligibleBundlers;

// Main execution loop
let isInitialRun = !localStorage.getItem('lastRunTimestamp');

async function mainLoop() {
    while (true) { // Run continuously
        console.log(`Starting analysis. Initial run: ${isInitialRun}`);
        await fetchBundlerData(isInitialRun);
        isInitialRun = false; // After the first run, set to false for subsequent runs
        localStorage.setItem('lastRunTimestamp', Date.now().toString());
        // No explicit delay here, relies on await to let other events run
    }
}

mainLoop(); // Run immediately on load