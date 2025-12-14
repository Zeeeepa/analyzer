# AI Chat Automation for Maxun

A comprehensive automation framework for interacting with multiple AI chat platforms simultaneously. Built on top of Maxun's powerful web automation capabilities.

## 🎯 Features

- ✅ **Multi-Platform Support**: Automate 6 major AI chat platforms
  - K2Think.ai
  - Qwen (chat.qwen.ai)
  - DeepSeek (chat.deepseek.com)
  - Grok (grok.com)
  - Z.ai (chat.z.ai)
  - Mistral AI (chat.mistral.ai)

- ⚡ **Parallel & Sequential Execution**: Send messages to all platforms simultaneously or one by one
- 🔐 **Secure Credential Management**: Environment variable-based configuration
- 🚀 **RESTful API**: Integrate with your applications via HTTP endpoints
- 📊 **CLI Tool**: Command-line interface for manual testing and automation
- 🎨 **TypeScript**: Fully typed for better development experience
- 🔄 **Retry Logic**: Built-in retry mechanisms for resilience
- 📝 **Comprehensive Logging**: Track all automation activities

## 📋 Prerequisites

- Node.js >= 16.x
- TypeScript >= 5.x
- Playwright (automatically installed)
- Valid credentials for the AI platforms you want to automate

## 🚀 Quick Start

### 1. Installation

```bash
cd ai-chat-automation
npm install
```

### 2. Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` file:

```env
# K2Think.ai
K2THINK_EMAIL=developer@pixelium.uk
K2THINK_PASSWORD=developer123

# Qwen
QWEN_EMAIL=developer@pixelium.uk
QWEN_PASSWORD=developer1

# DeepSeek
DEEPSEEK_EMAIL=zeeeepa+1@gmail.com
DEEPSEEK_PASSWORD=developer123

# Grok
GROK_EMAIL=developer@pixelium.uk
GROK_PASSWORD=developer123

# Z.ai
ZAI_EMAIL=developer@pixelium.uk
ZAI_PASSWORD=developer123

# Mistral
MISTRAL_EMAIL=developer@pixelium.uk
MISTRAL_PASSWORD=develooper123

# Browser Settings
HEADLESS=true
TIMEOUT=30000
```

### 3. Build

```bash
npm run build
```

## 💻 Usage

### CLI Tool

#### List Available Platforms

```bash
npm run cli list
```

#### Send Message to All Platforms

```bash
npm run cli send "how are you"
```

#### Send Message to Specific Platform

```bash
npm run cli send "hello" --platform K2Think
```

#### Send Sequentially (More Stable)

```bash
npm run cli send "how are you" --sequential
```

#### Run Quick Test

```bash
npm run cli test
```

### Example Script

Run the pre-built example that sends "how are you" to all platforms:

```bash
npm run send-all
```

Or with custom message:

```bash
npm run dev "What is artificial intelligence?"
```

### API Integration

The automation framework integrates with Maxun's existing API server. After building the project, the following endpoints become available:

#### 1. Get Available Platforms

```bash
GET /api/chat/platforms
Authorization: Bearer YOUR_API_KEY
```

Response:
```json
{
  "success": true,
  "platforms": ["K2Think", "Qwen", "DeepSeek", "Grok", "ZAi", "Mistral"],
  "count": 6
}
```

#### 2. Send Message to Specific Platform

```bash
POST /api/chat/send
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "platform": "K2Think",
  "message": "how are you"
}
```

Response:
```json
{
  "platform": "K2Think",
  "success": true,
  "message": "how are you",
  "response": "I'm doing well, thank you for asking! How can I help you today?",
  "timestamp": "2024-01-01T12:00:00.000Z",
  "duration": 5234
}
```

#### 3. Send Message to All Platforms

```bash
POST /api/chat/send-all
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "message": "how are you",
  "sequential": false
}
```

Response:
```json
{
  "success": true,
  "message": "how are you",
  "results": [
    {
      "platform": "K2Think",
      "success": true,
      "response": "I'm doing well!",
      "duration": 5234,
      "timestamp": "2024-01-01T12:00:00.000Z"
    },
    ...
  ],
  "summary": {
    "total": 6,
    "successful": 6,
    "failed": 0
  }
}
```

## 📚 Programmatic Usage

```typescript
import { ChatOrchestrator } from './ChatOrchestrator';

const orchestrator = new ChatOrchestrator();

// Send to specific platform
const result = await orchestrator.sendToPlatform('K2Think', 'how are you');
console.log(result);

// Send to all platforms (parallel)
const results = await orchestrator.sendToAll('how are you');
console.log(results);

// Send to all platforms (sequential)
const sequentialResults = await orchestrator.sendToAllSequential('how are you');
console.log(sequentialResults);

// Check available platforms
const platforms = orchestrator.getAvailablePlatforms();
console.log('Available:', platforms);
```

## 🏗️ Architecture

```
ai-chat-automation/
├── adapters/               # Platform-specific implementations
│   ├── BaseChatAdapter.ts  # Abstract base class (in types/)
│   ├── K2ThinkAdapter.ts
│   ├── QwenAdapter.ts
│   ├── DeepSeekAdapter.ts
│   ├── GrokAdapter.ts
│   ├── ZAiAdapter.ts
│   └── MistralAdapter.ts
├── types/                  # TypeScript interfaces
│   └── index.ts           # Base types & abstract class
├── examples/              # Usage examples
│   ├── send-to-all.ts    # Batch sending script
│   └── cli.ts            # CLI tool
├── ChatOrchestrator.ts   # Main coordination class
├── package.json
├── tsconfig.json
└── README.md
```

### How It Works

1. **BaseChatAdapter**: Abstract class defining the contract for all platform adapters
2. **Platform Adapters**: Concrete implementations for each AI chat platform
3. **ChatOrchestrator**: Coordinates multiple adapters and manages execution
4. **API Layer**: RESTful endpoints integrated with Maxun's server

## 🔧 Configuration Options

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `*_EMAIL` | Email for each platform | - | Yes (per platform) |
| `*_PASSWORD` | Password for each platform | - | Yes (per platform) |
| `HEADLESS` | Run browser in headless mode | `true` | No |
| `TIMEOUT` | Request timeout in milliseconds | `30000` | No |

### Adapter Configuration

Each adapter accepts:

```typescript
{
  credentials: {
    email: string;
    password: string;
  },
  headless?: boolean;      // Default: true
  timeout?: number;        // Default: 30000
  retryAttempts?: number;  // Default: 3
}
```

## ⚠️ Important Notes

### Security

- **Never commit your `.env` file**  - it contains sensitive credentials
- Use environment variables in production
- Consider using secret management services for production deployments
- Rotate credentials regularly

### Terms of Service

- Ensure your use case complies with each platform's Terms of Service
- Some platforms may prohibit automated access
- Consider using official APIs where available
- Implement rate limiting and respectful delays

### Reliability

- Web automation can be fragile due to UI changes
- Platforms may implement anti-bot measures
- Success rates may vary by platform
- Monitor and update selectors as platforms evolve

### Performance

- Parallel execution is faster but more resource-intensive
- Sequential execution is more stable and reliable
- Each platform interaction takes 5-15 seconds typically
- Browser instances consume ~100-300MB RAM each

## 🐛 Troubleshooting

### Issue: "Platform not found or not configured"

**Solution**: Check that credentials are properly set in `.env` file

### Issue: "Could not find chat input"

**Solution**: The platform's UI may have changed. Update selectors in the adapter

### Issue: "Timeout" errors

**Solution**: Increase `TIMEOUT` value in `.env` or check network connectivity

### Issue: Login fails

**Solution**: 
- Verify credentials are correct
- Check if platform requires captcha or 2FA
- Try logging in manually to check for account issues

### Issue: "ChatOrchestrator not found"

**Solution**: Run `npm run build` to compile TypeScript code

## 📊 Response Format

All chat operations return a standardized response:

```typescript
{
  platform: string;      // Platform name
  success: boolean;      // Whether operation succeeded
  message?: string;      // Original message sent
  response?: string;     // AI response received
  error?: string;        // Error message if failed
  timestamp: Date;       // When operation completed
  duration: number;      // Time taken in milliseconds
}
```

## 🧪 Testing

Run the test command to verify all platforms:

```bash
npm run cli test
```

This sends "how are you" to all configured platforms and displays results.

## 📈 Future Enhancements

- [ ] Add support for more AI platforms
- [ ] Implement conversation history tracking
- [ ] Add image/file upload support
- [ ] Create web dashboard for monitoring
- [ ] Add webhook notifications
- [ ] Implement caching for faster responses
- [ ] Add support for streaming responses

## 🤝 Contributing

Contributions are welcome! To add support for a new platform:

1. Create a new adapter in `adapters/` extending `BaseChatAdapter`
2. Implement all required methods
3. Add configuration to `ChatOrchestrator`
4. Update documentation

## 📄 License

AGPL-3.0 - See LICENSE file for details

## 🙏 Acknowledgments

Built with:
- Playwright for browser automation
- Maxun for web scraping infrastructure
- TypeScript for type safety

## 📞 Support

- Create an issue on GitHub
- Check Maxun documentation: https://docs.maxun.dev
- Join Maxun Discord: https://discord.gg/5GbPjBUkws

---

**Note**: This automation framework is for educational and authorized use only. Always respect platform Terms of Service and rate limits.

