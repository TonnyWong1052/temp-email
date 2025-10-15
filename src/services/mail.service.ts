import fetch from 'node-fetch';
import { config } from '../config';
import { Mail, MailApiResponse } from '../types';
import { codeService } from './code.service';

export class MailService {
  /**
   * 從郵箱API獲取郵件
   */
  async fetchMails(email: string): Promise<Mail[]> {
    try {
      const url = `${config.emailApiUrl}?email=${encodeURIComponent(email)}`;
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = (await response.json()) as MailApiResponse;

      if (!data.emails || data.emails.length === 0) {
        return [];
      }

      // 轉換為Mail格式
      return data.emails.map((emailData, index) => {
        const mail: Mail = {
          id: this.generateMailId(email, index),
          emailToken: '', // 將在存儲時設置
          from: emailData.from || 'unknown',
          to: email,
          subject: emailData.subject || '(No Subject)',
          content: emailData.content || '',
          receivedAt: emailData.date ? new Date(emailData.date) : new Date(),
          read: false,
        };

        // 提取驗證碼
        const codes = codeService.extractCodes(mail.content);
        if (codes.length > 0) {
          mail.codes = codes;
        }

        return mail;
      });
    } catch (error) {
      console.error('Failed to fetch mails:', error);
      return [];
    }
  }

  /**
   * 等待新郵件 (輪詢)
   */
  async waitForNewMail(
    email: string,
    sinceDate: Date,
    timeout: number = 30
  ): Promise<Mail[]> {
    const startTime = Date.now();
    const checkInterval = config.mailCheckInterval * 1000; // 轉為毫秒
    const timeoutMs = timeout * 1000;

    while (Date.now() - startTime < timeoutMs) {
      const mails = await this.fetchMails(email);

      // 過濾出新郵件
      const newMails = mails.filter((mail) => mail.receivedAt > sinceDate);

      if (newMails.length > 0) {
        return newMails;
      }

      // 等待後再檢查
      await this.sleep(checkInterval);
    }

    return []; // 超時，無新郵件
  }

  /**
   * 生成郵件ID
   */
  private generateMailId(email: string, index: number): string {
    const timestamp = Date.now();
    return `${email.replace(/@/g, '_')}_${timestamp}_${index}`;
  }

  /**
   * 睡眠函數
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * 從郵件內容中查找URL
   */
  extractUrls(content: string): string[] {
    const urlRegex = /https?:\/\/[^\s<>"']+/g;
    return content.match(urlRegex) || [];
  }

  /**
   * 格式化郵件為純文本
   */
  formatAsText(mail: Mail): string {
    return `
From: ${mail.from}
To: ${mail.to}
Subject: ${mail.subject}
Date: ${mail.receivedAt.toISOString()}

${mail.content}
    `.trim();
  }
}

export const mailService = new MailService();
