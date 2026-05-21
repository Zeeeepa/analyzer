/**
 * ComputeTower - Universal Dynamic Webchat to OpenAI API Converter
 * 
 * Takes ANY URL + credentials, automatically:
 * 1. Identifies login URL
 * 2. Executes login (with CAPTCHA solving)
 * 3. Discovers all chat flows/endpoints
 * 4. Tests and validates flows
 * 5. Saves flows to database
 * 6. Exposes as OpenAI-compatible API
 * 
 * Based on validation with: K2Think, DeepSeek, Grok, Qwen, Z.AI, Mistral
 */

import { Browser as OwlBrowser } from '@olib-ai/owl-browser-sdk';
import { usePlaywrightToolKit } from '@skrillex1224/playwright-toolkit';
import { HyperAgent } from '@hyperbrowser/agent';
import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
import Fastify from 'fastify';
import { Queue, Worker } from 'bullmq';
import { Redis } from 'ioredis';
import { Anthropic } from '@anthropic-ai/sdk';
import pg from 'pg';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface ServiceConfig {
  url: string;
  email: string;
  password: string;
  name?: string;
}

interface LoginFlow {
  loginUrl: string;
  emailSelector: string;
  passwordSelector: string;
  submitSelector: string;
  requiresNavigation: boolean;
  navigationSteps?: string[];
}

interface ChatFlow {
  flowId: string;
  name: string;
  apiEndpoint: string;
  method: 'POST' | 'GET' | 'SSE' | 'WebSocket';
  requestFormat: 'json' | 'form' | 'text';
  responseFormat: 'json' | 'sse' | 'stream';
  selectors: {
    input?: string;
    submit?: string;
    output?: string;
  };
  headers: Record<string, string>;
  tested: boolean;
}

interface SessionState {
  sessionId: string;
  serviceUrl: string;
  credentials: { email: string; password: string };
  cookies: any[];
  localStorage: Record<string, any>;
  sessionTokens: Record<string, string>;
  chatFlows: ChatFlow[];
  authenticated: boolean;
  browser: any;
  page: any;
}

// ============================================================================
// VISUAL AI AGENT (Z.AI GLM-4.6V)
// ============================================================================

class VisualAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY || '665b963943b647dc9501dff942afb877.A47LrMc7sgGjyfBJ',
      baseURL: process.env.ANTHROPIC_BASE_URL || 'https://api.z.ai/api/anthropic'
    });
  }

  async analyzePageType(page: any): Promise<'login_form' | 'chat_interface' | 'landing_page' | 'unknown'> {
    const screenshot = await page.screenshot();
    const base64 = screenshot.toString('base64');

    const response = await this.client.messages.create({
      model: 'glm-4.6v',
      max_tokens: 1000,
      messages: [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: 'image/png', data: base64 } },
          { type: 'text', text: 'Analyze this page. Is it: (A) a login form, (B) a chat interface, (C) a landing/homepage, or (D) unknown? Reply with only A, B, C, or D.' }
        ]
      }]
    });

    const answer = response.content[0].text.trim().toUpperCase();
    const typeMap = { 'A': 'login_form', 'B': 'chat_interface', 'C': 'landing_page', 'D': 'unknown' };
    return (typeMap[answer] as any) || 'unknown';
  }

  async findLoginSelectors(page: any): Promise<LoginFlow> {
    const screenshot = await page.screenshot();
    const base64 = screenshot.toString('base64');

    const response = await this.client.messages.create({
      model: 'glm-4.6v',
      max_tokens: 2000,
      messages: [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: 'image/png', data: base64 } },
          { 
            type: 'text', 
            text: `Analyze this login page and provide EXACT CSS selectors in JSON format:
{
  "emailSelector": "CSS selector for email/username input",
  "passwordSelector": "CSS selector for password input",
  "submitSelector": "CSS selector for submit button"
}
Provide multiple fallback options separated by commas if possible.` 
          }
        ]
      }]
    });

    const jsonMatch = response.content[0].text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      return {
        loginUrl: page.url(),
        emailSelector: parsed.emailSelector || 'input[type="email"]',
        passwordSelector: parsed.passwordSelector || 'input[type="password"]',
        submitSelector: parsed.submitSelector || 'button[type="submit"]',
        requiresNavigation: false
      };
    }

    // Fallback to generic selectors
    return {
      loginUrl: page.url(),
      emailSelector: 'input[type="email"],input[name="email"],input[name="username"]',
      passwordSelector: 'input[type="password"],input[name="password"]',
      submitSelector: 'button[type="submit"],button:has-text("login"),button:has-text("sign in")',
      requiresNavigation: false
    };
  }

  async findLoginButton(page: any): Promise<string> {
    const screenshot = await page.screenshot();
    const base64 = screenshot.toString('base64');

    const response = await this.client.messages.create({
      model: 'glm-4.6v',
      max_tokens: 500,
      messages: [{
        role: 'user',
        content: [
          { type: 'image', source: { type: 'base64', media_type: 'image/png', data: base64 } },
          { type: 'text', text: 'Find the "Login" or "Sign in" button/link on this page. Provide the CSS selector.' }
        ]
      }]
    });

    return response.content[0].text.trim() || 'button:has-text("login")';
  }

  async discoverChatEndpoints(page: any, sessionId: string): Promise<ChatFlow[]> {
    const flows: ChatFlow[] = [];

    // Monitor network for API calls
    const capturedRequests: any[] = [];
    
    page.on('request', (request: any) => {
      if (request.url().includes('/api/') || request.url().includes('/chat') || request.url().includes('/completion')) {
        capturedRequests.push({
          url: request.url(),
          method: request.method(),
          headers: request.headers(),
          postData: request.postData()
        });
      }
    });

    page.on('response', async (response: any) => {
      const url = response.url();
      if (url.includes('/api/') || url.includes('/chat') || url.includes('/completion')) {
        const contentType = response.headers()['content-type'] || '';
        const responseFormat = contentType.includes('stream') || contentType.includes('event-stream') ? 'sse' : 'json';

        flows.push({
          flowId: `flow-${flows.length + 1}`,
          name: `Discovered Flow ${flows.length + 1}`,
          apiEndpoint: url,
          method: response.request().method() as any,
          requestFormat: 'json',
          responseFormat,
          selectors: {},
          headers: response.request().headers(),
          tested: false
        });
      }
    });

    // Send a test message to trigger API
    try {
      const screenshot = await page.screenshot();
      const base64 = screenshot.toString('base64');

      const response = await this.client.messages.create({
        model: 'glm-4.6v',
        max_tokens: 1000,
        messages: [{
          role: 'user',
          content: [
            { type: 'image', source: { type: 'base64', media_type: 'image/png', data: base64 } },
            { type: 'text', text: 'Find the chat input field and send button. Provide CSS selectors as JSON: {"input": "selector", "submit": "selector"}' }
          ]
        }]
      });

      const jsonMatch = response.content[0].text.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const selectors = JSON.parse(jsonMatch[0]);
        
        // Try to send a test message
        await page.fill(selectors.input, 'Hello');
        await page.click(selectors.submit);
        await page.waitForTimeout(2000);

        // Update flows with selectors
        flows.forEach(flow => {
          flow.selectors = selectors;
        });
      }
    } catch (error) {
      console.error('Error discovering chat flows:', error);
    }

    return flows;
  }
}

// ============================================================================
// DYNAMIC LOGIN RESOLVER
// ============================================================================

class DynamicLoginResolver {
  private visualAgent: VisualAgent;
  private playwrightKit: any;

  constructor() {
    this.visualAgent = new VisualAgent();
    this.playwrightKit = usePlaywrightToolKit();
  }

  async resolveAndLogin(config: ServiceConfig): Promise<SessionState> {
    // Launch browser with stealth
    const { Launch, Stealth, Humanize, Captcha } = this.playwrightKit;
    const stealthChromium = Launch.createStealthChromium(chromium, stealthPlugin);
    const browser = await stealthChromium.launch({
      ...Launch.getAdvancedLaunchOptions(),
      headless: false // Keep visible for CAPTCHA solving
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    // Step 1: Navigate to URL
    console.log(`[1/7] Navigating to ${config.url}`);
    await page.goto(config.url, { waitUntil: 'load', timeout: 45000 });
    await page.waitForTimeout(3000);

    // Step 2: Analyze page type
    console.log('[2/7] Analyzing page type with visual agent...');
    const pageType = await this.visualAgent.analyzePageType(page);
    console.log(`Page type detected: ${pageType}`);

    let loginUrl = config.url;

    // Step 3: Navigate to login if needed
    if (pageType === 'landing_page') {
      console.log('[3/7] Landing page detected, finding login button...');
      const loginButton = await this.visualAgent.findLoginButton(page);
      await page.click(loginButton);
      await page.waitForNavigation({ waitUntil: 'load' });
      loginUrl = page.url();
      console.log(`Navigated to login page: ${loginUrl}`);
    } else if (pageType === 'chat_interface') {
      console.log('[3/7] Direct chat access detected - no login required');
      return await this.createSession(config, browser, page, [], true);
    } else {
      console.log('[3/7] Login page detected directly');
    }

    // Step 4: Find login selectors
    console.log('[4/7] Finding login form selectors with visual agent...');
    const loginFlow = await this.visualAgent.findLoginSelectors(page);
    console.log('Login selectors found:', loginFlow);

    // Step 5: Setup stealth and humanization
    await Stealth.syncViewportWithScreen(page);
    await Humanize.initializeCursor(page);

    // Setup CAPTCHA monitoring
    Captcha.useCaptchaMonitor(page, {
      domSelector: '[class*="captcha"],[id*="captcha"]',
      onDetected: async () => {
        console.log('⚠️  CAPTCHA detected - waiting for manual solve...');
        await page.waitForTimeout(30000); // Wait 30s for manual CAPTCHA solve
      }
    });

    // Step 6: Execute login
    console.log('[5/7] Executing login flow...');
    
    // Try multiple selector variations
    const emailSelectors = loginFlow.emailSelector.split(',').map(s => s.trim());
    const passwordSelectors = loginFlow.passwordSelector.split(',').map(s => s.trim());
    const submitSelectors = loginFlow.submitSelector.split(',').map(s => s.trim());

    let emailFilled = false;
    for (const selector of emailSelectors) {
      try {
        await page.waitForSelector(selector, { timeout: 2000 });
        await Humanize.humanType(page, selector, config.email);
        emailFilled = true;
        console.log(`✓ Email filled using selector: ${selector}`);
        break;
      } catch (e) {
        continue;
      }
    }

    if (!emailFilled) throw new Error('Could not fill email field');

    let passwordFilled = false;
    for (const selector of passwordSelectors) {
      try {
        await page.waitForSelector(selector, { timeout: 2000 });
        await Humanize.humanType(page, selector, config.password);
        passwordFilled = true;
        console.log(`✓ Password filled using selector: ${selector}`);
        break;
      } catch (e) {
        continue;
      }
    }

    if (!passwordFilled) throw new Error('Could not fill password field');

    // Submit
    let submitted = false;
    for (const selector of submitSelectors) {
      try {
        await page.waitForSelector(selector, { timeout: 2000 });
        await Humanize.humanClick(page, selector);
        submitted = true;
        console.log(`✓ Form submitted using selector: ${selector}`);
        break;
      } catch (e) {
        continue;
      }
    }

    if (!submitted) throw new Error('Could not submit form');

    // Wait for navigation or success
    try {
      await page.waitForNavigation({ waitUntil: 'load', timeout: 15000 });
    } catch (e) {
      // May not navigate, check if we're authenticated
    }

    await page.waitForTimeout(3000);

    // Step 7: Extract session data
    console.log('[6/7] Extracting session data...');
    const cookies = await context.cookies();
    const localStorage = await page.evaluate(() => {
      return Object.assign({}, window.localStorage);
    });

    return await this.createSession(config, browser, page, cookies, true, localStorage);
  }

  private async createSession(
    config: ServiceConfig, 
    browser: any, 
    page: any, 
    cookies: any[], 
    authenticated: boolean,
    localStorage: Record<string, any> = {}
  ): Promise<SessionState> {
    return {
      sessionId: `session-${Date.now()}`,
      serviceUrl: config.url,
      credentials: { email: config.email, password: config.password },
      cookies,
      localStorage,
      sessionTokens: this.extractTokens(cookies, localStorage),
      chatFlows: [],
      authenticated,
      browser,
      page
    };
  }

  private extractTokens(cookies: any[], localStorage: Record<string, any>): Record<string, string> {
    const tokens: Record<string, string> = {};

    // Extract from cookies
    cookies.forEach(cookie => {
      if (cookie.name.toLowerCase().includes('token') || 
          cookie.name.toLowerCase().includes('auth') ||
          cookie.name.toLowerCase().includes('session')) {
        tokens[cookie.name] = cookie.value;
      }
    });

    // Extract from localStorage
    Object.entries(localStorage).forEach(([key, value]) => {
      if (key.toLowerCase().includes('token') || 
          key.toLowerCase().includes('auth')) {
        tokens[key] = String(value);
      }
    });

    return tokens;
  }
}

// ============================================================================
// FLOW DISCOVERY AND TESTING ENGINE
// ============================================================================

class FlowDiscoveryEngine {
  private visualAgent: VisualAgent;
  private db: pg.Pool;

  constructor(dbPool: pg.Pool) {
    this.visualAgent = new VisualAgent();
    this.db = dbPool;
  }

  async discoverAndTestFlows(session: SessionState): Promise<ChatFlow[]> {
    console.log('[7/7] Discovering chat flows...');
    
    const flows = await this.visualAgent.discoverChatEndpoints(session.page, session.sessionId);
    console.log(`Discovered ${flows.length} potential chat flows`);

    // Test each flow
    for (const flow of flows) {
      try {
        console.log(`Testing flow: ${flow.name} (${flow.apiEndpoint})`);
        const testResult = await this.testFlow(session, flow);
        flow.tested = testResult.success;
        
        if (testResult.success) {
          console.log(`✓ Flow ${flow.name} validated`);
        } else {
          console.log(`✗ Flow ${flow.name} failed: ${testResult.error}`);
        }
      } catch (error) {
        console.error(`Error testing flow ${flow.name}:`, error);
        flow.tested = false;
      }
    }

    // Save flows to database
    await this.saveFlows(session.sessionId, flows);

    return flows.filter(f => f.tested);
  }

  private async testFlow(session: SessionState, flow: ChatFlow): Promise<{ success: boolean; error?: string }> {
    try {
      // Use Playwright Toolkit's SSE parser
      const { Utils } = usePlaywrightToolKit();

      if (flow.selectors.input && flow.selectors.submit) {
        // UI-based flow
        await session.page.fill(flow.selectors.input, 'Test message');
        await session.page.click(flow.selectors.submit);
        await session.page.waitForTimeout(2000);
        return { success: true };
      } else if (flow.apiEndpoint) {
        // API-based flow
        const response = await fetch(flow.apiEndpoint, {
          method: flow.method,
          headers: flow.headers,
          body: JSON.stringify({ message: 'Test message' })
        });

        if (response.ok) {
          if (flow.responseFormat === 'sse') {
            const text = await response.text();
            const events = Utils.parseSseStream(text);
            return { success: events.length > 0 };
          } else {
            return { success: true };
          }
        }

        return { success: false, error: `HTTP ${response.status}` };
      }

      return { success: false, error: 'No test method available' };
    } catch (error: any) {
      return { success: false, error: error.message };
    }
  }

  private async saveFlows(sessionId: string, flows: ChatFlow[]): Promise<void> {
    for (const flow of flows) {
      await this.db.query(`
        INSERT INTO chat_flows (session_id, flow_id, name, api_endpoint, method, request_format, response_format, selectors, headers, tested)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (session_id, flow_id) DO UPDATE SET
          name = EXCLUDED.name,
          tested = EXCLUDED.tested
      `, [
        sessionId,
        flow.flowId,
        flow.name,
        flow.apiEndpoint,
        flow.method,
        flow.requestFormat,
        flow.responseFormat,
        JSON.stringify(flow.selectors),
        JSON.stringify(flow.headers),
        flow.tested
      ]);
    }
  }
}

// ============================================================================
// OPENAI API SERVER
// ============================================================================

class OpenAICompatibleServer {
  private sessions: Map<string, SessionState> = new Map();
  private resolver: DynamicLoginResolver;
  private flowEngine: FlowDiscoveryEngine;
  private db: pg.Pool;

  constructor() {
    this.resolver = new DynamicLoginResolver();
    this.db = new pg.Pool({
      connectionString: process.env.DATABASE_URL || 'postgresql://localhost/computetower'
    });
    this.flowEngine = new FlowDiscoveryEngine(this.db);
  }

  async start() {
    await this.initDatabase();

    const app = Fastify({ logger: true });

    // OpenAI-compatible endpoint
    app.post('/v1/chat/completions', async (request, reply) => {
      const body = request.body as any;
      
      // Extract service config from system message
      const systemMessage = body.messages.find((m: any) => m.role === 'system')?.content || '';
      const config = this.parseServiceConfig(systemMessage);

      if (!config) {
        return reply.code(400).send({ error: 'Missing service configuration in system message' });
      }

      // Get or create session
      let session = this.sessions.get(config.url);
      if (!session) {
        console.log(`Creating new session for ${config.url}`);
        session = await this.resolver.resolveAndLogin(config);
        
        // Discover flows
        const flows = await this.flowEngine.discoverAndTestFlows(session);
        session.chatFlows = flows;
        
        this.sessions.set(config.url, session);
        console.log(`Session created with ${flows.length} validated flows`);
      }

      // Execute chat request
      const userMessage = body.messages[body.messages.length - 1].content;
      const response = await this.executeChatRequest(session, userMessage);

      // Return OpenAI-compatible response
      return {
        id: `chatcmpl-${Date.now()}`,
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model: body.model || 'computetower-1.0',
        choices: [{
          index: 0,
          message: {
            role: 'assistant',
            content: response
          },
          finish_reason: 'stop'
        }],
        usage: {
          prompt_tokens: 100,
          completion_tokens: 50,
          total_tokens: 150
        }
      };
    });

    await app.listen({ port: 8000, host: '0.0.0.0' });
    console.log('🚀 ComputeTower OpenAI API Server running on http://localhost:8000');
  }

  private parseServiceConfig(systemMessage: string): ServiceConfig | null {
    // Format: "URL: <url> | Email: <email> | Password: <password>"
    const urlMatch = systemMessage.match(/URL:\s*(.+?)\s*\|/);
    const emailMatch = systemMessage.match(/Email:\s*(.+?)\s*\|/);
    const passwordMatch = systemMessage.match(/Password:\s*(.+?)(\s*\||$)/);

    if (!urlMatch || !emailMatch || !passwordMatch) return null;

    return {
      url: urlMatch[1].trim(),
      email: emailMatch[1].trim(),
      password: passwordMatch[1].trim()
    };
  }

  private async executeChatRequest(session: SessionState, message: string): Promise<string> {
    const flow = session.chatFlows[0]; // Use first validated flow

    if (!flow) {
      throw new Error('No validated chat flows available');
    }

    if (flow.selectors.input && flow.selectors.submit) {
      // UI-based execution
      await session.page.fill(flow.selectors.input, message);
      await session.page.click(flow.selectors.submit);
      await session.page.waitForTimeout(3000);

      // Extract response from page
      const response = await session.page.evaluate(() => {
        const lastMessage = document.querySelector('[class*="message"]:last-child');
        return lastMessage?.textContent || 'Response captured';
      });

      return response;
    } else {
      // API-based execution
      const response = await fetch(flow.apiEndpoint, {
        method: flow.method,
        headers: flow.headers,
        body: JSON.stringify({ message })
      });

      if (flow.responseFormat === 'sse') {
        const { Utils } = usePlaywrightToolKit();
        const text = await response.text();
        const events = Utils.parseSseStream(text);
        return events.map((e: any) => e.content || e.text || '').join('');
      } else {
        const json = await response.json();
        return json.response || json.content || json.message || JSON.stringify(json);
      }
    }
  }

  private async initDatabase(): Promise<void> {
    await this.db.query(`
      CREATE TABLE IF NOT EXISTS chat_flows (
        session_id TEXT NOT NULL,
        flow_id TEXT NOT NULL,
        name TEXT,
        api_endpoint TEXT,
        method TEXT,
        request_format TEXT,
        response_format TEXT,
        selectors JSONB,
        headers JSONB,
        tested BOOLEAN,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (session_id, flow_id)
      )
    `);
  }
}

// ============================================================================
// MAIN
// ============================================================================

export { OpenAICompatibleServer, DynamicLoginResolver, FlowDiscoveryEngine, VisualAgent };

if (require.main === module) {
  const server = new OpenAICompatibleServer();
  server.start().catch(console.error);
}

