// Site-wide settings for the landing page, member hub and guide.
// Edit this file to change links and leaderboard data — no other code needs to change.
window.TANIX_CONFIG = {
    // TODO: replace with your real Telegram channel link.
    telegramUrl: 'https://t.me/YOUR_CHANNEL',

    // Best performers (podium). Order does not matter: the podium sorts by `roi`.
    // These are SAMPLE entries — replace with your verified monthly results.
    performersMonth: 'Last Month',
    performers: [
        { handle: '@AlexFx_VIP',  strategy: 'Scalping liquidity sweeps', roi: 412.5 },
        { handle: '@RohanTrades', strategy: 'Tanix AI gold trend',       roi: 288.1 },
        { handle: '@D_Leverage',  strategy: 'Session breakout rules',    roi: 215.4 },
    ],
};
