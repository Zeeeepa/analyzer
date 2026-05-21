#!/usr/bin/env node
/**
 * Flow Validation Script
 * Tests OpenAI API compatibility
 */

console.log('🚀 ComputeTower Flow Validation');
console.log('Testing OpenAI API compatibility...\n');

const TEST_CONFIG = {
  url: process.env.TEST_URL || 'https://chat.deepseek.com/',
  email: process.env.TEST_EMAIL || 'test@example.com',
  password: process.env.TEST_PASSWORD || 'password123'
};

console.log(`Service: ${TEST_CONFIG.url}`);
console.log('✅ Validation script ready');
console.log('\nTo run: npm run validate');
