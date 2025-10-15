import { Email, Mail } from '../types';

/**
 * 內存存儲服務
 * 所有數據存儲在內存中，重啟後會丟失
 */
export class StorageService {
  private emails: Map<string, Email> = new Map(); // token -> Email
  private mails: Map<string, Mail[]> = new Map(); // emailToken -> Mail[]
  private emailByAddress: Map<string, string> = new Map(); // address -> token

  /**
   * 保存郵箱
   */
  saveEmail(email: Email): void {
    this.emails.set(email.token, email);
    this.emailByAddress.set(email.address, email.token);
  }

  /**
   * 根據token獲取郵箱
   */
  getEmailByToken(token: string): Email | null {
    return this.emails.get(token) || null;
  }

  /**
   * 根據地址獲取郵箱
   */
  getEmailByAddress(address: string): Email | null {
    const token = this.emailByAddress.get(address);
    if (!token) return null;
    return this.getEmailByToken(token);
  }

  /**
   * 刪除郵箱
   */
  deleteEmail(token: string): boolean {
    const email = this.emails.get(token);
    if (!email) return false;

    this.emails.delete(token);
    this.emailByAddress.delete(email.address);
    this.mails.delete(token);
    return true;
  }

  /**
   * 獲取所有郵箱
   */
  getAllEmails(): Email[] {
    return Array.from(this.emails.values());
  }

  /**
   * 保存郵件
   */
  saveMails(emailToken: string, mails: Mail[]): void {
    // 為每封郵件設置emailToken
    mails.forEach((mail) => {
      mail.emailToken = emailToken;
    });

    const existingMails = this.mails.get(emailToken) || [];

    // 合併郵件，避免重複
    const mergedMails = [...existingMails];
    mails.forEach((newMail) => {
      const exists = existingMails.some((m) => m.id === newMail.id);
      if (!exists) {
        mergedMails.push(newMail);
      }
    });

    this.mails.set(emailToken, mergedMails);

    // 更新郵件數量
    const email = this.emails.get(emailToken);
    if (email) {
      email.mailCount = mergedMails.length;
    }
  }

  /**
   * 獲取郵件列表
   */
  getMails(emailToken: string, limit?: number, offset: number = 0): Mail[] {
    const mails = this.mails.get(emailToken) || [];

    // 按接收時間倒序排序
    const sorted = mails.sort(
      (a, b) => b.receivedAt.getTime() - a.receivedAt.getTime()
    );

    if (limit !== undefined) {
      return sorted.slice(offset, offset + limit);
    }

    return sorted.slice(offset);
  }

  /**
   * 獲取單封郵件
   */
  getMailById(emailToken: string, mailId: string): Mail | null {
    const mails = this.mails.get(emailToken) || [];
    return mails.find((m) => m.id === mailId) || null;
  }

  /**
   * 標記郵件為已讀
   */
  markAsRead(emailToken: string, mailId: string): boolean {
    const mail = this.getMailById(emailToken, mailId);
    if (!mail) return false;
    mail.read = true;
    return true;
  }

  /**
   * 獲取未讀郵件
   */
  getUnreadMails(emailToken: string): Mail[] {
    const mails = this.mails.get(emailToken) || [];
    return mails.filter((m) => !m.read);
  }

  /**
   * 清理過期郵箱
   */
  cleanupExpired(): number {
    let count = 0;
    const now = new Date();

    for (const [token, email] of this.emails.entries()) {
      if (email.expiresAt < now) {
        this.deleteEmail(token);
        count++;
      }
    }

    return count;
  }

  /**
   * 獲取統計信息
   */
  getStats() {
    const totalEmails = this.emails.size;
    const totalMails = Array.from(this.mails.values()).reduce(
      (sum, mails) => sum + mails.length,
      0
    );

    return {
      totalEmails,
      totalMails,
      activeEmails: totalEmails,
    };
  }
}

export const storageService = new StorageService();

// 每5分鐘清理一次過期郵箱
setInterval(() => {
  const count = storageService.cleanupExpired();
  if (count > 0) {
    console.log(`Cleaned up ${count} expired emails`);
  }
}, 5 * 60 * 1000);
