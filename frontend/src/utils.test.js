import { expect, test, describe } from 'vitest';
import {
  STATUS_LABEL,
  STATUS_STYLE,
  CATEGORY_LABEL,
  CATEGORY_COLOR,
  formatINR,
  formatDateTime,
  shortHash,
} from './utils';

describe('Label and Status Maps', () => {
  test('all statuses have both a label and a style', () => {
    const statusKeys = new Set([...Object.keys(STATUS_LABEL), ...Object.keys(STATUS_STYLE)]);
    
    // Explicitly define the exhaustive list of known statuses from the backend.
    const expectedStatuses = [
      'PENDING',
      'SCHEDULED',
      'PENDING_CONFIRMATION',
      'AWAITING_CUSTOMER',
      'RECOVERED',
      'EXHAUSTED',
      'CANCELLED'
    ];
    
    // Check that we have styling and labels for every single expected status
    expectedStatuses.forEach(status => {
      expect(STATUS_LABEL).toHaveProperty(status);
      expect(STATUS_STYLE).toHaveProperty(status);
    });

    // Check that there are no unmatched keys
    statusKeys.forEach(status => {
      expect(STATUS_LABEL[status], `Missing label for ${status}`).toBeDefined();
      expect(STATUS_STYLE[status], `Missing style for ${status}`).toBeDefined();
    });
  });

  test('all categories have both a label and a color', () => {
    const categoryKeys = new Set([...Object.keys(CATEGORY_LABEL), ...Object.keys(CATEGORY_COLOR)]);
    
    const expectedCategories = [
      'INSUFFICIENT_FUNDS',
      'BANK_OUTAGE',
      'MANDATE_EXPIRED',
      'MANDATE_CANCELLED',
      'UNKNOWN'
    ];
    
    expectedCategories.forEach(category => {
      expect(CATEGORY_LABEL).toHaveProperty(category);
      expect(CATEGORY_COLOR).toHaveProperty(category);
    });

    categoryKeys.forEach(category => {
      expect(CATEGORY_LABEL[category], `Missing label for ${category}`).toBeDefined();
      expect(CATEGORY_COLOR[category], `Missing color for ${category}`).toBeDefined();
    });
  });
});

describe('Formatting Utilities', () => {
  test('formatINR formats currency numbers into INR representation', () => {
    const formatted = formatINR(5000);
    expect(formatted).toContain('5,000');
    expect(formatINR(0)).toContain('0');
    expect(formatINR(null)).toContain('0');
  });

  test('formatDateTime returns em-dash for empty input and formats ISO string in IST', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime('')).toBe('—');
    const result = formatDateTime('2026-11-24T10:30:00Z');
    expect(result).toMatch(/24/);
    expect(result).toMatch(/Nov/);
  });

  test('shortHash shortens long hash strings correctly', () => {
    expect(shortHash(null)).toBe('');
    expect(shortHash('')).toBe('');
    const fullHash = 'abcdef1234567890abcdef1234567890abcdef12';
    const shortened = shortHash(fullHash);
    expect(shortened).toBe('abcdef12…abcdef12'.slice(0, 8) + '…' + fullHash.slice(-6));
    expect(shortened).toContain('…');
  });
});
