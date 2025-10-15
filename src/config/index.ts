import dotenv from 'dotenv';

dotenv.config();

export const config = {
  port: parseInt(process.env.PORT || '3000', 10),
  nodeEnv: process.env.NODE_ENV || 'development',

  // Database
  databasePath: process.env.DATABASE_PATH || './data/emails.db',

  // Email Configuration
  emailApiUrl: process.env.EMAIL_API_URL || 'https://mail.chatgpt.org.uk/api/get-emails',
  emailTtl: parseInt(process.env.EMAIL_TTL || '3600', 10),
  mailCheckInterval: parseInt(process.env.MAIL_CHECK_INTERVAL || '5', 10),
  maxMailsPerEmail: parseInt(process.env.MAX_MAILS_PER_EMAIL || '50', 10),

  // Rate Limiting
  rateLimitWindow: parseInt(process.env.RATE_LIMIT_WINDOW || '3600000', 10),
  rateLimitMaxRequests: parseInt(process.env.RATE_LIMIT_MAX_REQUESTS || '100', 10),

  // CORS
  corsOrigin: process.env.CORS_ORIGIN || '*',
};

// 可用的郵箱域名
export const EMAIL_DOMAINS = [
  'chatgptuk.pp.ua',
  'freemails.pp.ua',
  'email.gravityengine.cc',
  'gravityengine.cc',
  '3littlemiracles.com',
  'almiswelfare.org',
  'gyan-netra.com',
  'iraniandsa.org',
  '14club.org.uk',
  'aard.org.uk',
  'allumhall.co.uk',
  'cade.org.uk',
  'caye.org.uk',
  'cketrust.org',
  'club106.org.uk',
  'cok.org.uk',
  'cwetg.co.uk',
  'goleudy.org.uk',
  'hhe.org.uk',
  'hottchurch.org.uk',
];
