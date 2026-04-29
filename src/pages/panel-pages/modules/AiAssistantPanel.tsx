import { useState } from 'react'
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

  if (!farmerId) {
    return <p className="panel-empty">Farmer profile not found. Complete registration to chat with the assistant.</p>
  }

  return (
    <div className="panel-cards">
      <article className="panel-card panel-card--chat">
        <div className="panel-card__head">
          <h3>Contextual Chat</h3>
          <span className="panel-card__metric">Live</span>
        </div>
        <p>Ask about yield, health, weather, or market trends.</p>
        <div className="panel-chat">
          <div className="panel-chat__messages">
            {messages.length === 0 ? <p className="panel-empty">Start the conversation…</p> : null}
            {messages.map((msg, index) => (
              <div key={`${msg.role}-${index}`} className={`panel-chat__bubble panel-chat__bubble--${msg.role}`}>
                {msg.content || (msg.role === 'bot' && streaming ? '...' : '')}
              </div>
            ))}
          </div>
          <div className="panel-chat__input">
            <input
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask KishanSaathi..."
            />
            <button type="button" className="panel-mapbox__button" onClick={handleSend} disabled={streaming}>
              {streaming ? 'Streaming...' : 'Send'}
            </button>
          </div>
        </div>
      </article>
    </div>
  )
}

export default AiAssistantPanel
