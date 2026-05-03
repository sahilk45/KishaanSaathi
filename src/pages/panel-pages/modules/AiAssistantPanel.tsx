import { useEffect, useRef, useState, useCallback } from 'react'
import { Mic, MicOff, Send } from 'lucide-react'
import { streamChat } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'

type ChatMessage = {
  role: 'user' | 'bot'
  content: string
  timestamp?: string
}

// ── Web Speech API types ──────────────────────────────────────────────────────
type SpeechRecognitionEvent = Event & {
  results: { [index: number]: { [index: number]: { transcript: string } } }
}
type SpeechRecognitionInstance = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onerror: ((e: Event) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionInstance
    webkitSpeechRecognition?: new () => SpeechRecognitionInstance
  }
}

const LANG_CODES: Record<string, string> = { EN: 'en-IN', HI: 'hi-IN', PA: 'pa-IN' }

// ── Chat history API ──────────────────────────────────────────────────────────
const API_BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')

async function fetchChatHistory(farmerId: string, fieldId: string): Promise<ChatMessage[]> {
  try {
    const threadId = `thread-${farmerId}-${fieldId}`
    const res = await fetch(`${API_BASE}/chat/history?thread_id=${encodeURIComponent(threadId)}`)
    if (!res.ok) return []
    const data = await res.json() as { messages?: { role: string; content: string; timestamp?: string }[] }
    return (data.messages ?? []).map((m) => ({
      role: m.role === 'human' ? 'user' : 'bot',
      content: m.content,
      timestamp: m.timestamp,
    }))
  } catch {
    return []
  }
}

const AiAssistantPanel = () => {
  const { panel, language } = useLanguage()
  const t = panel.panel.aiAssistant
  const { pushToast } = useToast()
  const { farmerId, fieldId } = useSession()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [listening, setListening] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Load history when field changes ──────────────────────────────────────
  useEffect(() => {
    if (!farmerId || !fieldId) return
    let active = true
    setHistoryLoading(true)
    setMessages([])
    fetchChatHistory(farmerId, fieldId).then((history) => {
      if (!active) return
      setMessages(history)
      setHistoryLoading(false)
    })
    return () => { active = false }
  }, [farmerId, fieldId])

  // ── Send message ──────────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const message = input.trim()
    if (!message || !farmerId) return
    const threadId = fieldId ? `thread-${farmerId}-${fieldId}` : `thread-${farmerId}`

    setMessages((prev) => [...prev, { role: 'user', content: message }, { role: 'bot', content: '' }])
    setInput('')
    setStreaming(true)

    try {
      await streamChat(farmerId, message, threadId, (token) => {
        setMessages((prev) => {
          const next = [...prev]
          const last = next.length - 1
          if (last >= 0 && next[last].role === 'bot') {
            next[last] = { ...next[last], content: next[last].content + token }
          }
          return next
        })
      })
    } catch (error) {
      pushToast(getLocalizedApiError(error, { errors: { chatbot: t.farmerNotFound } } as never), 'error')
    } finally {
      setStreaming(false)
    }
  }, [input, farmerId, fieldId, pushToast, t])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  // ── Voice-to-text ─────────────────────────────────────────────────────────
  const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
  const voiceSupported = !!SpeechRecognitionAPI

  const toggleListening = useCallback(() => {
    if (!SpeechRecognitionAPI) {
      pushToast(t.micNotSupported, 'error')
      return
    }
    if (listening) {
      recognitionRef.current?.stop()
      setListening(false)
      return
    }
    const rec = new SpeechRecognitionAPI()
    rec.lang = LANG_CODES[language] ?? 'en-IN'
    rec.continuous = false
    rec.interimResults = false
    rec.onresult = (e: SpeechRecognitionEvent) => {
      const transcript = e.results[0][0].transcript
      setInput((prev) => (prev ? `${prev} ${transcript}` : transcript))
    }
    rec.onerror = () => setListening(false)
    rec.onend = () => setListening(false)
    recognitionRef.current = rec
    rec.start()
    setListening(true)
  }, [SpeechRecognitionAPI, language, listening, pushToast, t.micNotSupported])

  if (!farmerId) {
    return <p className="panel-empty">{t.farmerNotFound}</p>
  }

  return (
    <div className="panel-chat-fullscreen">
      <div className="panel-chat-fullscreen__messages">
        {historyLoading ? (
          <p className="panel-empty">{t.loadingHistory}</p>
        ) : messages.length === 0 ? (
          <div className="panel-chat-fullscreen__welcome">
            <h2>{t.welcome}</h2>
            <p>{t.welcomeDescription}</p>
            {fieldId && <p style={{ fontSize: '0.75rem', opacity: 0.6, marginTop: 4 }}>{t.perField}</p>}
            <div className="panel-chat-fullscreen__suggestions">
              <button type="button" onClick={() => setInput('Mera health score kya hai?')}>{t.suggestHealthScore}</button>
              <button type="button" onClick={() => setInput('Aaj mausam kaisa hai?')}>{t.suggestWeather}</button>
              <button type="button" onClick={() => setInput('Wheat ka mandi price batao')}>{t.suggestWheatPrice}</button>
              <button type="button" onClick={() => setInput('Suggest best crop for my field')}>{t.suggestBestCrop}</button>
            </div>
          </div>
        ) : null}

        {messages.map((msg, index) => (
          <div key={`${msg.role}-${index}`} className={`panel-chat-fullscreen__bubble panel-chat-fullscreen__bubble--${msg.role}`}>
            <span className="panel-chat-fullscreen__role">{msg.role === 'user' ? t.you : t.kisanSaathi}</span>
            <div className="panel-chat-fullscreen__text">
              {msg.content || (msg.role === 'bot' && streaming ? '●●●' : '')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="panel-chat-fullscreen__input-bar">
        {voiceSupported && (
          <button
            type="button"
            className={`panel-chat-fullscreen__mic${listening ? ' panel-chat-fullscreen__mic--active' : ''}`}
            onClick={toggleListening}
            title={listening ? t.listening : 'Voice input'}
            aria-label={listening ? t.listening : 'Start voice input'}
          >
            {listening ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
        )}
        <textarea
          value={listening ? `${input} 🎤` : input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={listening ? t.listening : t.inputPlaceholder}
          rows={1}
          disabled={streaming || listening}
        />
        <button
          type="button"
          className="panel-chat-fullscreen__send"
          onClick={handleSend}
          disabled={streaming || !input.trim() || listening}
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}

export default AiAssistantPanel
