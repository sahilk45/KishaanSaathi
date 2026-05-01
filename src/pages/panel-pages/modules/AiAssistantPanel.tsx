import { useEffect, useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { streamChat } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'

type ChatMessage = {
  role: 'user' | 'bot'
  content: string
}

const AiAssistantPanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { farmerId } = useSession()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const message = input.trim()
    if (!message || !farmerId) return

    setMessages((prev) => [...prev, { role: 'user', content: message }, { role: 'bot', content: '' }])
    setInput('')
    setStreaming(true)

    try {
      await streamChat(farmerId, message, (token) => {
        setMessages((prev) => {
          const next = [...prev]
          const lastIndex = next.length - 1
          if (lastIndex >= 0 && next[lastIndex].role === 'bot') {
            next[lastIndex] = { ...next[lastIndex], content: next[lastIndex].content + token }
          }
          return next
        })
      })
    } catch (error) {
      const messageText = getLocalizedApiError(error, content)
      pushToast(messageText, 'error')
    } finally {
      setStreaming(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!farmerId) {
    return <p className="panel-empty">Farmer profile not found. Complete registration to chat with the assistant.</p>
  }

  return (
    <div className="panel-chat-fullscreen">
      <div className="panel-chat-fullscreen__messages">
        {messages.length === 0 ? (
          <div className="panel-chat-fullscreen__welcome">
            <h2>🌾 KisanSaathi AI</h2>
            <p>Ask about your crop health, weather, market prices, or get farming advice.</p>
            <div className="panel-chat-fullscreen__suggestions">
              <button type="button" onClick={() => setInput('Mera health score kya hai?')}>My health score?</button>
              <button type="button" onClick={() => setInput('Aaj mausam kaisa hai?')}>Today's weather?</button>
              <button type="button" onClick={() => setInput('Wheat ka mandi price batao')}>Wheat market price?</button>
              <button type="button" onClick={() => setInput('Suggest best crop for my field')}>Best crop suggestion?</button>
            </div>
          </div>
        ) : null}
        {messages.map((msg, index) => (
          <div key={`${msg.role}-${index}`} className={`panel-chat-fullscreen__bubble panel-chat-fullscreen__bubble--${msg.role}`}>
            <span className="panel-chat-fullscreen__role">{msg.role === 'user' ? 'You' : 'KisanSaathi'}</span>
            <div className="panel-chat-fullscreen__text">
              {msg.content || (msg.role === 'bot' && streaming ? '●●●' : '')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="panel-chat-fullscreen__input-bar">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask KisanSaathi anything..."
          rows={1}
          disabled={streaming}
        />
        <button type="button" className="panel-chat-fullscreen__send" onClick={handleSend} disabled={streaming || !input.trim()}>
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}

export default AiAssistantPanel
