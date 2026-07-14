import { describe, expect, it } from 'vitest';
import { getParsedApiError } from '../error';

describe('API timeout attribution', () => {
  it('distinguishes an Axios client wait timeout from an upstream timeout', () => {
    const clientTimeout = getParsedApiError({
      code: 'ECONNABORTED',
      message: 'timeout of 30000ms exceeded',
    });
    const upstreamTimeout = getParsedApiError({
      response: {
        status: 504,
        data: { error: 'vision_timeout', message: 'Vision provider read timeout' },
      },
      message: 'Request failed with status code 504',
    });

    expect(clientTimeout.category).toBe('client_timeout');
    expect(clientTimeout.title).toBe('浏览器等待响应超时');
    expect(upstreamTimeout.category).toBe('upstream_timeout');
    expect(upstreamTimeout.title).toBe('连接上游服务超时');
  });
});
