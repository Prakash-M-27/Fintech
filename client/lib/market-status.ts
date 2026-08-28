export type MarketState = 'OPEN' | 'CLOSED' | 'PRE-MARKET';

export interface MarketStatusInfo {
  state: MarketState;
  countdown: string;
}

const formatCountdown = (ms: number): string => {
  const totalMinutes = Math.floor(ms / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
};

export const getMarketStatus = (assetKey: 'nifty' | 'gold' | 'usd'): MarketStatusInfo => {
  // Get current UTC time and convert to IST (UTC+5:30)
  const now = new Date();
  const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
  const istOffset = 5.5 * 60 * 60000;
  const istNow = new Date(utcMs + istOffset);

  const day = istNow.getDay();
  const isWeekend = day === 0 || day === 6; // Sunday = 0, Saturday = 6
  
  const currentHour = istNow.getHours();
  const currentMinute = istNow.getMinutes();
  const currentTimeInMinutes = currentHour * 60 + currentMinute;

  let openHour = 9, openMin = 0, closeHour = 15, closeMin = 30;

  if (assetKey === 'nifty') {
    openHour = 9; openMin = 15;
    closeHour = 15; closeMin = 30;
  } else if (assetKey === 'gold') {
    openHour = 9; openMin = 0;
    closeHour = 23; closeMin = 30;
  } else if (assetKey === 'usd') {
    openHour = 9; openMin = 0;
    closeHour = 17; closeMin = 0;
  }

  const openTimeInMinutes = openHour * 60 + openMin;
  const closeTimeInMinutes = closeHour * 60 + closeMin;

  if (isWeekend) {
    // If weekend, it's closed. Countdown to Monday open.
    const daysToAdd = day === 6 ? 2 : 1;
    const nextOpen = new Date(istNow);
    nextOpen.setDate(istNow.getDate() + daysToAdd);
    nextOpen.setHours(openHour, openMin, 0, 0);
    return {
      state: 'CLOSED',
      countdown: `Opens in ${formatCountdown(nextOpen.getTime() - istNow.getTime())}`
    };
  }

  if (currentTimeInMinutes < openTimeInMinutes) {
    // Before market opens today
    const preMarketStart = openTimeInMinutes - 60;
    if (currentTimeInMinutes >= preMarketStart) {
      return {
        state: 'PRE-MARKET',
        countdown: `Opens in ${formatCountdown((openTimeInMinutes - currentTimeInMinutes) * 60000)}`
      };
    }
    return {
      state: 'CLOSED',
      countdown: `Opens in ${formatCountdown((openTimeInMinutes - currentTimeInMinutes) * 60000)}`
    };
  } else if (currentTimeInMinutes >= openTimeInMinutes && currentTimeInMinutes < closeTimeInMinutes) {
    // Market is open
    return {
      state: 'OPEN',
      countdown: `Closes in ${formatCountdown((closeTimeInMinutes - currentTimeInMinutes) * 60000)}`
    };
  } else {
    // Market is closed for today, countdown to tomorrow open
    let daysToAdd = 1;
    if (day === 5) {
      daysToAdd = 3; // Friday -> Monday
    }
    const nextOpen = new Date(istNow);
    nextOpen.setDate(istNow.getDate() + daysToAdd);
    nextOpen.setHours(openHour, openMin, 0, 0);
    return {
      state: 'CLOSED',
      countdown: `Opens in ${formatCountdown(nextOpen.getTime() - istNow.getTime())}`
    };
  }
};

export const getOverallMarketStatus = (): MarketStatusInfo => {
  // Use NIFTY as the baseline for overall Indian market status
  return getMarketStatus('nifty');
};
