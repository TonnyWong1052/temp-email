/**
 * Cloudflare Email Worker - 接收並存儲郵件到 Workers KV
 *
 * 此 Worker 攔截通過 Cloudflare Email Routing 轉發的郵件，
 * 解析郵件內容並存儲到 Workers KV，供 FastAPI 後端讀取。
 */

export default {
  /**
   * Email handler - 處理接收到的郵件
   * @param {EmailMessage} message - 郵件消息對象
   * @param {Object} env - 環境變量（包含 KV binding）
   * @param {Object} ctx - 執行上下文
   */
  async email(message, env, ctx) {
    try {
      console.log(`[Email Worker] Received email to: ${message.to}`);

      // 提取郵件基本信息
      const from = message.from;
      const to = message.to;
      const subject = message.headers.get("subject") || "(No Subject)";
      const date = message.headers.get("date") || new Date().toISOString();

      // 讀取郵件原始內容（以 latin1 保留字節不失真）
      const rawContent = await streamToArrayBuffer(message.raw);
      const rawTextLatin1 = bytesToLatin1(rawContent);

      // 解析郵件（處理 charset 與 transfer-encoding）
      const parsed = parseEmail(rawTextLatin1);

      // 構建郵件對象
      const emailData = {
        id: generateMailId(to, from, subject, date),
        from: from,
        to: to,
        subject: subject,
        content: parsed.text,
        html_content: parsed.html,
        received_at: new Date(date).toISOString(),
        raw_headers: Object.fromEntries(message.headers),
        timestamp: Date.now()
      };

      // 存儲到 KV
      // Key 格式: mail:{email_address}:{timestamp}
      const kvKey = `mail:${to}:${Date.now()}`;
      await env.EMAIL_STORAGE.put(
        kvKey,
        JSON.stringify(emailData),
        {
          expirationTtl: 3600, // 1 小時後過期
          metadata: {
            email: to,
            from: from,
            subject: subject,
            receivedAt: emailData.received_at
          }
        }
      );

      // 更新郵箱的郵件索引列表
      await updateMailIndex(env.EMAIL_STORAGE, to, kvKey, emailData);

      console.log(`[Email Worker] Stored email with key: ${kvKey}`);

      // 不轉發郵件，只存儲
      // 如果需要轉發，可以添加: await message.forward(destinationEmail);

    } catch (error) {
      console.error(`[Email Worker] Error processing email:`, error);
      // 即使出錯也不拋出異常，避免影響郵件接收
    }
  }
};

/**
 * 將 ReadableStream 轉換為 ArrayBuffer
 */
async function streamToArrayBuffer(stream) {
  const reader = stream.getReader();
  const chunks = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  // 合併所有 chunks
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;

  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return result.buffer;
}

/**
 * 簡單的郵件解析器
 * 提取純文本和 HTML 內容
 */
function parseEmail(rawContent) {
  const result = {
    text: "",
    html: ""
  };

  // 查找 Content-Type 邊界
  const boundaryMatch = rawContent.match(/boundary="?([^"\s;]+)"?/i);

  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = rawContent.split(`--${boundary}`);

    for (const part of parts) {
      // 分離 headers 與 body
      const splitIndex = findHeaderBodySeparator(part);
      if (splitIndex === -1) continue;
      const headersRaw = part.slice(0, splitIndex);
      let bodyRaw = part.slice(splitIndex);

      const headers = parseHeaders(headersRaw);
      const ctype = headers['content-type'] || '';
      const cte = (headers['content-transfer-encoding'] || '').toLowerCase();
      const charset = getCharset(ctype);

      // 邊界段落可能以結束標記結尾
      bodyRaw = bodyRaw.replace(/--\s*$/, '').trim();

      const decoded = decodeBody(bodyRaw, cte, charset);

      if (/text\/plain/i.test(ctype)) {
        result.text = decoded;
      } else if (/text\/html/i.test(ctype)) {
        result.html = decoded;
      }
    }
  } else {
    // 單部分郵件
    const splitIndex = findHeaderBodySeparator(rawContent);
    if (splitIndex !== -1) {
      const headersRaw = rawContent.slice(0, splitIndex);
      let bodyRaw = rawContent.slice(splitIndex);
      const headers = parseHeaders(headersRaw);
      const ctype = headers['content-type'] || '';
      const cte = (headers['content-transfer-encoding'] || '').toLowerCase();
      const charset = getCharset(ctype);
      const decoded = decodeBody(bodyRaw, cte, charset);

      if (/text\/html/i.test(ctype) || decoded.includes('<html')) {
        result.html = decoded;
        result.text = extractTextFromHtml(decoded);
      } else {
        result.text = decoded;
      }
    }
  }

  return result;
}

function bytesToLatin1(buf) {
  const u8 = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
  return s;
}

function findHeaderBodySeparator(s) {
  const idx1 = s.indexOf('\r\n\r\n');
  if (idx1 !== -1) return idx1 + 4; // start of body after CRLFCRLF
  const idx2 = s.indexOf('\n\n');
  if (idx2 !== -1) return idx2 + 2;
  const idx3 = s.indexOf('\r\r');
  if (idx3 !== -1) return idx3 + 2;
  return -1;
}

/**
 * 從 HTML 提取純文本
 */
function extractTextFromHtml(html) {
  return html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * 解碼 Base64 編碼的內容
 */
function decodeBase64(base64String) {
  try {
    // 移除所有空白字符（換行、空格等）
    const cleanedBase64 = base64String.replace(/[\r\n\s]/g, '');

    // 使用 atob 解碼 base64
    const decodedString = atob(cleanedBase64);

    // 將字節字符串轉換為 UTF-8 文本
    const bytes = new Uint8Array(decodedString.split('').map(char => char.charCodeAt(0)));
    return new TextDecoder('utf-8').decode(bytes);
  } catch (error) {
    console.error('[Email Worker] Base64 decode error:', error);
    // 如果解碼失敗，返回原始內容
    return base64String;
  }
}

function parseHeaders(headersRaw) {
  const headers = {};
  const lines = headersRaw.replace(/\r/g, '').split('\n');
  let current = '';
  for (const line of lines) {
    if (/^\s/.test(line)) {
      current += ' ' + line.trim();
    } else {
      if (current) {
        const idx = current.indexOf(':');
        if (idx > -1) headers[current.slice(0, idx).toLowerCase()] = current.slice(idx + 1).trim();
      }
      current = line;
    }
  }
  if (current) {
    const idx = current.indexOf(':');
    if (idx > -1) headers[current.slice(0, idx).toLowerCase()] = current.slice(idx + 1).trim();
  }
  return headers;
}

function getCharset(contentType) {
  const m = contentType.match(/charset\s*=\s*"?([^";\s]+)/i);
  const cs = (m ? m[1] : 'utf-8').toLowerCase();
  if (cs === 'utf8') return 'utf-8';
  if (cs === 'gbk' || cs === 'gb2312') return 'gb18030';
  return cs;
}

function decodeQuotedPrintable(input) {
  // 移除軟換行 =\r\n 或 =\n
  const softBreaksRemoved = input.replace(/=\r?\n/g, '');
  const bytes = [];
  for (let i = 0; i < softBreaksRemoved.length; i++) {
    const ch = softBreaksRemoved[i];
    if (ch === '=') {
      const hex = softBreaksRemoved.substr(i + 1, 2);
      if (/^[0-9A-Fa-f]{2}$/.test(hex)) {
        bytes.push(parseInt(hex, 16));
        i += 2;
      } else {
        bytes.push('='.charCodeAt(0));
      }
    } else {
      bytes.push(ch.charCodeAt(0));
    }
  }
  return new Uint8Array(bytes);
}

function tryDecode(bytes, charset) {
  try {
    return new TextDecoder(charset).decode(bytes);
  } catch (e) {
    try {
      return new TextDecoder('utf-8').decode(bytes);
    } catch (e2) {
      return new TextDecoder('latin1').decode(bytes);
    }
  }
}

function decodeBody(bodyRaw, cte, charset) {
  let text = '';
  if (cte === 'base64') {
    // 先按 base64 → bytes，再根據 charset 解碼
    const cleaned = bodyRaw.replace(/[\r\n\s]/g, '');
    try {
      const bin = atob(cleaned);
      const bytes = new Uint8Array(Array.from(bin, c => c.charCodeAt(0)));
      text = tryDecode(bytes, charset);
    } catch (e) {
      text = decodeBase64(bodyRaw);
    }
  } else if (cte === 'quoted-printable') {
    const bytes = decodeQuotedPrintable(bodyRaw);
    text = tryDecode(bytes, charset);
  } else {
    // 8bit/7bit/binary：按 latin1 → bytes，再根據 charset 解碼
    const bytes = new Uint8Array(Array.from(bodyRaw, c => c.charCodeAt(0)));
    text = tryDecode(bytes, charset);
  }
  return text.trim();
}

/**
 * 生成穩定的郵件 ID
 */
function generateMailId(to, from, subject, date) {
  const uniqueString = `${to}:${from}:${subject}:${date}`;
  return `mail_${simpleHash(uniqueString)}`;
}

/**
 * 簡單的哈希函數
 */
function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36).substring(0, 16);
}

/**
 * 更新郵箱的郵件索引
 * 維護每個郵箱地址的郵件列表
 */
async function updateMailIndex(kv, emailAddress, mailKey, emailData) {
  const indexKey = `index:${emailAddress}`;

  try {
    // 獲取現有索引
    const existingIndex = await kv.get(indexKey, { type: "json" });
    const mailList = existingIndex?.mails || [];

    // 添加新郵件
    mailList.push({
      key: mailKey,
      id: emailData.id,
      from: emailData.from,
      subject: emailData.subject,
      receivedAt: emailData.received_at,
      timestamp: emailData.timestamp,
      content_preview: emailData.content.substring(0, 500)  // 儲存內容摘要 (前 500 字符)
    });

    // 限制列表大小（最多保留 50 封）
    const limitedList = mailList.slice(-50);

    // 更新索引
    await kv.put(
      indexKey,
      JSON.stringify({
        email: emailAddress,
        mails: limitedList,
        lastUpdate: new Date().toISOString()
      }),
      {
        expirationTtl: 3600 // 1 小時後過期
      }
    );
  } catch (error) {
    console.error(`[Email Worker] Error updating mail index:`, error);
  }
}
