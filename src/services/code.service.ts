import { Code } from '../types';

export class CodeService {
  /**
   * 從文本中提取驗證碼
   */
  extractCodes(text: string): Code[] {
    const codes: Code[] = [];

    // 1. 純數字驗證碼 (4-8位)
    const numericPatterns = [
      { pattern: /\b\d{6}\b/g, type: 'numeric' as const, length: 6, confidence: 0.9 },
      { pattern: /\b\d{4}\b/g, type: 'numeric' as const, length: 4, confidence: 0.8 },
      { pattern: /\b\d{8}\b/g, type: 'numeric' as const, length: 8, confidence: 0.85 },
    ];

    for (const { pattern, type, length, confidence } of numericPatterns) {
      const matches = text.match(pattern);
      if (matches) {
        matches.forEach((code) => {
          if (!this.isDuplicate(codes, code)) {
            codes.push({
              code,
              type,
              length,
              pattern: pattern.source,
              confidence,
            });
          }
        });
      }
    }

    // 2. 字母數字混合 (6-10位)
    const alphanumericPatterns = [
      {
        pattern: /\b[A-Z0-9]{6,10}\b/g,
        type: 'alphanumeric' as const,
        confidence: 0.75,
      },
    ];

    for (const { pattern, type, confidence } of alphanumericPatterns) {
      const matches = text.match(pattern);
      if (matches) {
        matches.forEach((code) => {
          if (!this.isDuplicate(codes, code)) {
            codes.push({
              code,
              type,
              length: code.length,
              pattern: pattern.source,
              confidence,
            });
          }
        });
      }
    }

    // 3. 常見驗證碼關鍵詞附近
    const contextPatterns = [
      /(?:code|Code|驗證碼|验证码|OTP|otp)[\s:：]*([A-Z0-9]{4,10})/gi,
      /(?:your|Your)\s+(?:verification|code)[\s:：]*([A-Z0-9]{4,10})/gi,
      /(?:token|Token)[\s:：]*([A-Za-z0-9_-]{10,40})/gi,
    ];

    for (const pattern of contextPatterns) {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const code = match[1];
        if (!this.isDuplicate(codes, code)) {
          const type = code.length > 15 ? 'token' : 'alphanumeric';
          codes.push({
            code,
            type: type as 'alphanumeric' | 'token',
            length: code.length,
            pattern: pattern.source,
            confidence: 0.95, // 上下文關鍵詞提高置信度
          });
        }
      }
    }

    // 4. URL參數中的驗證碼
    const urlPatterns = [
      /[?&](?:code|token|verify)=([A-Za-z0-9_-]+)/gi,
    ];

    for (const pattern of urlPatterns) {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const code = match[1];
        if (!this.isDuplicate(codes, code) && code.length >= 6) {
          codes.push({
            code,
            type: code.length > 15 ? 'token' : 'alphanumeric',
            length: code.length,
            pattern: pattern.source,
            confidence: 0.85,
          });
        }
      }
    }

    // 按置信度排序
    return codes.sort((a, b) => b.confidence - a.confidence);
  }

  /**
   * 檢查是否重複
   */
  private isDuplicate(codes: Code[], code: string): boolean {
    return codes.some((c) => c.code === code);
  }

  /**
   * 從HTML中提取驗證碼
   */
  extractFromHtml(html: string): Code[] {
    // 移除HTML標籤
    const text = html.replace(/<[^>]*>/g, ' ');
    // 解碼HTML實體
    const decoded = this.decodeHtmlEntities(text);
    return this.extractCodes(decoded);
  }

  /**
   * 解碼HTML實體
   */
  private decodeHtmlEntities(text: string): string {
    const entities: Record<string, string> = {
      '&amp;': '&',
      '&lt;': '<',
      '&gt;': '>',
      '&quot;': '"',
      '&#39;': "'",
      '&nbsp;': ' ',
    };

    return text.replace(/&[^;]+;/g, (entity) => entities[entity] || entity);
  }
}

export const codeService = new CodeService();
