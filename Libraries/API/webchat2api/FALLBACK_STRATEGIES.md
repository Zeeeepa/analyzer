# Universal Dynamic Web Chat Automation Framework - Fallback Strategies

## 🛡️ **Comprehensive Error Handling & Recovery**

This document defines fallback mechanisms for every critical operation in the system.

---

## 🎯 **Fallback Philosophy**

**Core Principles:**
1. **Never fail permanently** - Always have a fallback
2. **Graceful degradation** - Reduce functionality rather than crash
3. **Automatic recovery** - Self-heal without human intervention (when possible)
4. **Clear error communication** - Tell user what went wrong and what we're doing
5. **Timeouts everywhere** - No infinite waits

---

## 1️⃣ **Vision API Failures**

### **Primary Method:** GLM-4.5v API

### **Failure Scenarios:**
- API timeout (>10s)
- API rate limit reached
- API authentication failure
- Invalid response format
- Low confidence scores (<70%)

### **Fallback Chain:**

**Level 1: Retry with exponential backoff**
```
Attempt 1: Wait 2s, retry
Attempt 2: Wait 4s, retry
Attempt 3: Wait 8s, retry
Max attempts: 3
```

**Level 2: Use cached selectors (if available)**
```go
if cache := GetSelectorCache(domain); cache != nil {
    if time.Since(cache.LastValidated) < 7*24*time.Hour {
        // Use cached selectors
        return cache.Selectors, nil
    }
}
```

**Level 3: Use hardcoded templates**
```go
templates := GetProviderTemplates(domain)
if templates != nil {
    // Common providers like ChatGPT, Claude
    return templates.Selectors, nil
}
```

**Level 4: Fallback to OmniParser (if installed)**
```go
if omniParser.Available() {
    return omniParser.DetectElements(screenshot)
}
```

**Level 5: Manual configuration**
```go
// Return error asking user to provide selectors manually
return nil, errors.New("Vision failed. Please configure selectors manually via API")
```

### **Recovery Actions:**
- Log failure details
- Notify monitoring system
- Increment failure counter
- If 10 consecutive failures: Disable vision temporarily

---

## 2️⃣ **Selector Not Found**

### **Primary Method:** Use discovered/cached selector

### **Failure Scenarios:**
- Element doesn't exist (removed from DOM)
- Element hidden/not visible
- Element within iframe
- Multiple matching elements (ambiguous)
- Page structure changed

### **Fallback Chain:**

**Level 1: Wait and retry**
```go
for i := 0; i < 3; i++ {
    element := page.QuerySelector(selector)
    if element != nil {
        return element, nil
    }
    time.Sleep(1 * time.Second)
}
```

**Level 2: Try fallback selectors**
```go
for _, fallbackSelector := range cache.Fallbacks {
    element := page.QuerySelector(fallbackSelector)
    if element != nil {
        return element, nil
    }
}
```

**Level 3: Scroll and retry**
```go
// Element might be below fold
page.Evaluate(`window.scrollTo(0, document.body.scrollHeight)`)
time.Sleep(500 * time.Millisecond)
element := page.QuerySelector(selector)
```

**Level 4: Switch to iframe (if applicable)**
```go
frames := page.Frames()
for _, frame := range frames {
    element := frame.QuerySelector(selector)
    if element != nil {
        return element, nil
    }
}
```

**Level 5: Re-discover with vision**
```go
screenshot := page.Screenshot()
newSelectors := visionEngine.DetectElements(screenshot)
updateSelectorCache(domain, newSelectors)
return page.QuerySelector(newSelectors.Input), nil
```

**Level 6: Use JavaScript fallback**
```go
// Last resort: Find element by text content or attributes
jsCode := `document.querySelector('textarea, input[type="text"]')`
element := page.Evaluate(jsCode)
```

### **Recovery Actions:**
- Invalidate selector cache
- Mark selector as unstable
- Increment failure counter
- Trigger re-discovery if 3 consecutive failures

---

## 3️⃣ **Response Not Detected**

### **Primary Method:** Network interception (SSE/WebSocket/XHR)

### **Failure Scenarios:**
- No network traffic detected
- Stream interrupted mid-response
- Malformed response chunks
- Unexpected content-type
- Response timeout (>60s)

### **Fallback Chain:**

**Level 1: Extend timeout**
```go
timeout := 30 * time.Second
for i := 0; i < 3; i++ {
    response, err := waitForResponse(timeout)
    if err == nil {
        return response, nil
    }
    timeout *= 2 // 30s → 60s → 120s
}
```

**Level 2: Switch to DOM observation**
```go
if networkInterceptor.Failed() {
    return domObserver.CaptureResponse(responseContainer)
}
```

**Level 3: Visual polling**
```go
// Screenshot-based detection (expensive)
previousText := ""
for i := 0; i < 30; i++ {
    currentText := page.InnerText(responseContainer)
    if currentText != previousText && !isTyping(page) {
        return currentText, nil
    }
    previousText = currentText
    time.Sleep(2 * time.Second)
}
```

**Level 4: Re-send message**
```go
// Response failed, try sending again
clickElement(submitButton)
return waitForResponse(30 * time.Second)
```

**Level 5: Restart session**
```go
// Nuclear option: Create fresh session
session.Destroy()
newSession := CreateSession(providerID)
return newSession.SendMessage(message)
```

### **Recovery Actions:**
- Log response method used
- Update streaming method if different
- Clear response buffer
- Mark session as potentially unhealthy

---

## 4️⃣ **CAPTCHA Encountered**

### **Primary Method:** Auto-solve with 2Captcha API

### **Failure Scenarios:**
- 2Captcha API down
- API key invalid/expired
- CAPTCHA type unsupported
- Solution incorrect
- Timeout (>120s)

### **Fallback Chain:**

**Level 1: Retry with 2Captcha**
```go
for i := 0; i < 2; i++ {
    solution, err := captchaSolver.Solve(captchaInfo, pageURL)
    if err == nil {
        applySolution(page, solution)
        if !captchaStillPresent(page) {
            return nil // Success
        }
    }
}
```

**Level 2: Try alternative solving service**
```go
if anticaptcha.Available() {
    solution := anticaptcha.Solve(captchaInfo, pageURL)
    applySolution(page, solution)
}
```

**Level 3: Pause and log for manual intervention**
```go
// Save page state
saveBrowserState(session)
notifyAdmin("CAPTCHA requires manual solving", {
    "provider": providerID,
    "session": sessionID,
    "screenshot": page.Screenshot(),
})
// Wait for admin to solve (with timeout)
return waitForManualIntervention(5 * time.Minute)
```

**Level 4: Skip provider temporarily**
```go
// Mark provider as requiring CAPTCHA
provider.Status = "captcha_blocked"
provider.LastFailure = time.Now()
// Try alternative provider if available
return useAlternativeProvider(message)
```

### **Recovery Actions:**
- Log CAPTCHA type and frequency
- Alert if CAPTCHAs increase suddenly (possible detection)
- Rotate sessions more frequently
- Consider adding delays between requests

---

## 5️⃣ **Authentication Failures**

### **Primary Method:** Automated login with credentials

### **Failure Scenarios:**
- Invalid credentials
- 2FA required
- Session expired
- Cookie invalid
- Account locked

### **Fallback Chain:**

**Level 1: Clear cookies and re-authenticate**
```go
context.ClearCookies()
return loginFlow.Authenticate(credentials)
```

**Level 2: Wait for 2FA (if applicable)**
```go
if detected2FA(page) {
    code := waitFor2FACode(email) // From email/SMS service
    fill2FACode(page, code)
    return validateAuthentication(page)
}
```

**Level 3: Use existing session token**
```go
if cache := getSessionToken(providerID); cache != nil {
    context.AddCookies(cache.Cookies)
    return validateAuthentication(page)
}
```

**Level 4: Request new credentials**
```go
// Notify that credentials are invalid
return errors.New("Authentication failed. Please update credentials via API")
```

### **Recovery Actions:**
- Mark provider as authentication_failed
- Clear invalid session tokens
- Log authentication failure reason
- Notify admin if credential update needed

---

## 6️⃣ **Network Timeouts**

### **Primary Method:** Standard HTTP request

### **Failure Scenarios:**
- Connection timeout
- DNS resolution failure
- SSL certificate error
- Network unreachable

### **Fallback Chain:**

**Level 1: Exponential backoff retry**
```go
backoff := 2 * time.Second
for i := 0; i < 3; i++ {
    _, err := page.Goto(url)
    if err == nil {
        return nil
    }
    time.Sleep(backoff)
    backoff *= 2
}
```

**Level 2: Use proxy (if available)**
```go
if proxy := getProxy(); proxy != nil {
    context := browser.NewContext(playwright.BrowserNewContextOptions{
        Proxy: &playwright.Proxy{Server: proxy.URL},
    })
    return context.NewPage()
}
```

**Level 3: Try alternative URL**
```go
alternativeURLs := []string{
    provider.URL,
    provider.MirrorURL,
    provider.BackupURL,
}
for _, url := range alternativeURLs {
    _, err := page.Goto(url)
    if err == nil {
        return nil
    }
}
```

**Level 4: Mark provider as unreachable**
```go
provider.Status = "unreachable"
provider.LastChecked = time.Now()
return errors.New("Provider temporarily unreachable")
```

### **Recovery Actions:**
- Log network failure details
- Check provider health endpoint
- Notify monitoring system
- Schedule health check retry

---

## 7️⃣ **Session Pool Exhausted**

### **Primary Method:** Get available session from pool

### **Failure Scenarios:**
- All sessions in use
- Max sessions reached
- Pool empty
- Health check failures

### **Fallback Chain:**

**Level 1: Wait for available session**
```go
timeout := 30 * time.Second
select {
case session := <-pool.Available:
    return session, nil
case <-time.After(timeout):
    // Continue to Level 2
}
```

**Level 2: Create new session (if under limit)**
```go
if pool.Size() < pool.MaxSize {
    session := CreateSession(providerID)
    pool.Add(session)
    return session, nil
}
```

**Level 3: Recycle idle session**
```go
if idleSession := pool.GetIdleLongest(); idleSession != nil {
    idleSession.Reset()
    return idleSession, nil
}
```

**Level 4: Force-close oldest session**
```go
oldestSession := pool.GetOldest()
oldestSession.Destroy()
newSession := CreateSession(providerID)
return newSession, nil
```

**Level 5: Return error with retry-after**
```go
return nil, errors.New("Session pool exhausted. Retry after 30s")
```

### **Recovery Actions:**
- Monitor pool utilization
- Alert if consistently at max
- Consider increasing pool size
- Check for session leaks

---

## 8️⃣ **Streaming Response Incomplete**

### **Primary Method:** Capture complete stream

### **Failure Scenarios:**
- Stream closed prematurely
- Chunks missing
- [DONE] marker never sent
- Connection interrupted

### **Fallback Chain:**

**Level 1: Continue reading from buffer**
```go
buffer := []string{}
timeout := 5 * time.Second
for {
    chunk, err := stream.Read()
    if err == io.EOF || chunk == "[DONE]" {
        return strings.Join(buffer, ""), nil
    }
    buffer = append(buffer, chunk)
    // Reset timeout on each chunk
    time.Sleep(100 * time.Millisecond)
}
```

**Level 2: Detect visual completion**
```go
// Check if typing indicator disappeared
if !isTyping(page) && responseStable(page, 2*time.Second) {
    return page.InnerText(responseContainer), nil
}
```

**Level 3: Use partial response**
```go
// Return what we captured so far
if len(buffer) > 0 {
    return strings.Join(buffer, ""), errors.New("Response incomplete (partial)")
}
```

**Level 4: Re-request**
```go
// Clear previous response
clearResponseArea(page)
// Re-submit
clickElement(submitButton)
return waitForCompleteResponse(60 * time.Second)
```

### **Recovery Actions:**
- Log incomplete response frequency
- Check for network stability issues
- Adjust timeout thresholds
- Consider alternative detection method

---

## 9️⃣ **Rate Limiting**

### **Primary Method:** Normal request rate

### **Failure Scenarios:**
- 429 Too Many Requests
- Provider blocks IP temporarily
- Account rate limited
- Detected as bot

### **Fallback Chain:**

**Level 1: Respect Retry-After header**
```go
if retryAfter := response.Header.Get("Retry-After"); retryAfter != "" {
    delay, _ := strconv.Atoi(retryAfter)
    time.Sleep(time.Duration(delay) * time.Second)
    return retryRequest()
}
```

**Level 2: Exponential backoff**
```go
backoff := 60 * time.Second
for i := 0; i < 5; i++ {
    time.Sleep(backoff)
    if !isRateLimited() {
        return retryRequest()
    }
    backoff *= 2 // 60s → 120s → 240s → 480s → 960s
}
```

**Level 3: Rotate session**
```go
// Create new browser context (new IP via proxy)
newContext := createContextWithProxy()
return retryWithNewContext(newContext)
```

**Level 4: Queue request for later**
```go
// Add to delayed queue
queue.AddDelayed(request, 10*time.Minute)
return errors.New("Rate limited. Request queued for retry in 10 minutes")
```

### **Recovery Actions:**
- Log rate limit events
- Alert if rate limits increase
- Adjust request rate dynamically
- Consider adding request delays

---

## 🔟 **Graceful Degradation Matrix**

| Component | Primary | Fallback 1 | Fallback 2 | Fallback 3 | Final Fallback |
|-----------|---------|------------|------------|------------|----------------|
| Vision API | GLM-4.5v | Cache | Templates | OmniParser | Manual config |
| Selector | Discovered | Fallback list | Re-discover | JS search | Error |
| Response | Network | DOM observer | Visual poll | Re-send | New session |
| CAPTCHA | 2Captcha | Alt service | Manual | Skip provider | Error |
| Auth | Auto-login | Re-auth | Token | New creds | Error |
| Network | Direct | Retry | Proxy | Alt URL | Mark down |
| Session | Pool | Create new | Recycle | Force-close | Error |
| Stream | Full capture | Partial | Visual detect | Re-request | Error |
| Rate limit | Normal | Retry-After | Backoff | Rotate | Queue |

---

## 🎯 **Recovery Success Targets**

| Failure Type | Recovery Rate Target | Max Recovery Time |
|--------------|---------------------|-------------------|
| Vision API | >95% | 30s |
| Selector not found | >90% | 10s |
| Response detection | >95% | 60s |
| CAPTCHA | >85% | 120s |
| Authentication | >90% | 30s |
| Network timeout | >90% | 30s |
| Session pool | >99% | 5s |
| Incomplete stream | >90% | 30s |
| Rate limiting | >80% | 600s |

---

## 📊 **Monitoring & Alerting**

### **Metrics to Track:**
- Fallback trigger frequency
- Recovery success rate per component
- Average recovery time
- Failed recovery count (manual intervention needed)

### **Alerts:**
- **Critical:** Recovery rate <80% for 10 minutes
- **Warning:** Fallback triggered >50% of requests
- **Info:** Manual intervention required

---

**Version:** 1.0  
**Last Updated:** 2024-12-05  
**Status:** Comprehensive

