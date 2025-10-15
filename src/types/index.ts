// 郵箱模型
export interface Email {
  token: string;
  address: string;
  prefix: string;
  domain: string;
  createdAt: Date;
  expiresAt: Date;
  mailCount: number;
}

// 郵件模型
export interface Mail {
  id: string;
  emailToken: string;
  from: string;
  to: string;
  subject: string;
  content: string;
  htmlContent?: string;
  receivedAt: Date;
  read: boolean;
  codes?: Code[];
}

// 驗證碼模型
export interface Code {
  code: string;
  type: 'numeric' | 'alphanumeric' | 'token';
  length: number;
  pattern: string;
  confidence: number;
}

// API響應
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

// 郵件API響應
export interface MailApiResponse {
  emails?: Array<{
    from: string;
    subject: string;
    content: string;
    date?: string;
  }>;
}
