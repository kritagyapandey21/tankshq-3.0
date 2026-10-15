// Site-wide settings for the landing page, member hub and guide.
// Edit this file to change links and leaderboard data — no other code needs to change.
window.TANIX_CONFIG = {
    // TODO: replace with your real Telegram channel link.
    telegramUrl: 'https://t.me/YOUR_CHANNEL',
    // TODO: replace with your YouTube walkthrough link.
    youtubeUrl: 'https://youtube.com',

    // Best performers (podium). Order does not matter: the podium sorts by `roi`.
    // `photo` files are AI-generated placeholder faces (not real people). Replace with each
    // winner's own (consented) photo by overwriting assets/winner1.jpg, winner2.jpg, winner3.jpg.
    // These are SAMPLE entries — replace with your verified monthly results.
    performersMonth: 'Last Month',
    performers: [
        { handle: '@AlexFx_VIP',  strategy: 'Scalping liquidity sweeps', roi: 412.5, photo: 'assets/winner1.jpg' },
        { handle: '@RohanTrades', strategy: 'Tanix AI gold trend',       roi: 288.1, photo: 'assets/winner2.jpg' },
        { handle: '@D_Leverage',  strategy: 'Session breakout rules',    roi: 215.4, photo: 'assets/winner3.jpg' },
    ],
};
