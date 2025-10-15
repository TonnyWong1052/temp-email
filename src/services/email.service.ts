import { randomBytes } from 'crypto';
import { EMAIL_DOMAINS } from '../config';
import { Email } from '../types';
import { v4 as uuidv4 } from 'crypto';

export class EmailService {
  /**
   * 生成隨機郵箱地址
   */
  generateEmail(prefix?: string, domain?: string): Email {
    const token = this.generateToken();
    const emailPrefix = prefix || this.generateRandomPrefix();
    const emailDomain = domain || this.selectRandomDomain();
    const address = `${emailPrefix}@${emailDomain}`;

    const now = new Date();
    const expiresAt = new Date(now.getTime() + 3600 * 1000); // 1小時後過期

    return {
      token,
      address,
      prefix: emailPrefix,
      domain: emailDomain,
      createdAt: now,
      expiresAt,
      mailCount: 0,
    };
  }

  /**
   * 生成唯一Token
   */
  private generateToken(): string {
    return randomBytes(16).toString('hex');
  }

  /**
   * 生成隨機郵箱前綴 (12位十六進制)
   */
  private generateRandomPrefix(): string {
    return randomBytes(6).toString('hex');
  }

  /**
   * 隨機選擇一個域名
   */
  private selectRandomDomain(): string {
    const index = Math.floor(Math.random() * EMAIL_DOMAINS.length);
    return EMAIL_DOMAINS[index];
  }

  /**
   * 驗證郵箱格式
   */
  validateEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  /**
   * 檢查郵箱是否過期
   */
  isExpired(email: Email): boolean {
    return new Date() > email.expiresAt;
  }

  /**
   * 生成郵箱Web URL
   */
  getEmailWebUrl(email: string): string {
    return `https://mail.chatgpt.org.uk?email=${encodeURIComponent(email)}`;
  }
}

export const emailService = new EmailService();
