import { useState, useEffect } from 'react'
import '../styles/SettingsView.css'

interface SettingsTab {
  id: 'general' | 'memory' | 'channels' | 'scheduling' | 'workspace'
  label: string
  icon: string
}

interface WhatsAppConfig {
  configured: boolean
  phone_number_id?: string
}

interface MemorySettings {
  chunks_indexed: number
  model: string
}

interface SettingsViewProps {
  httpPort: number
}

export function SettingsView({ httpPort }: SettingsViewProps) {
  const [activeTab, setActiveTab] = useState<'general' | 'memory' | 'channels' | 'scheduling' | 'workspace'>('general')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const base = `http://127.0.0.1:${httpPort}`

  // State for each tab
  const [whatsappConfig, setWhatsappConfig] = useState<WhatsAppConfig | null>(null)
  const [memoryStats, setMemoryStats] = useState<MemorySettings | null>(null)
  const [workspacePath, setWorkspacePath] = useState('')
  const [defaultModel, setDefaultModel] = useState('')

  const tabs: SettingsTab[] = [
    { id: 'general', label: 'General', icon: '⚙️' },
    { id: 'memory', label: 'Memory', icon: '🧠' },
    { id: 'channels', label: 'Channels', icon: '📱' },
    { id: 'scheduling', label: 'Scheduling', icon: '🕐' },
    { id: 'workspace', label: 'Workspace', icon: '📁' },
  ]

  useEffect(() => {
    loadSettings()
  }, [activeTab, httpPort])

  const loadSettings = async () => {
    setLoading(true)
    setError(null)

    try {
      switch (activeTab) {
        case 'memory':
          const memRes = await fetch(`${base}/api/memory/stats`)
          if (memRes.ok) {
            const data = await memRes.json()
            setMemoryStats(data.stats)
          }
          break

        case 'channels':
          const whatsRes = await fetch(`${base}/api/whatsapp/config`)
          if (whatsRes.ok) {
            const data = await whatsRes.json()
            setWhatsappConfig(data)
          }
          break

        case 'workspace':
          const configRes = await fetch(`${base}/api/config`)
          if (configRes.ok) {
            const data = await configRes.json()
            setWorkspacePath(data.workspace_dir || '')
            setDefaultModel(data.default_model || '')
          }
          break
      }
    } catch (err) {
      setError(`Failed to load ${activeTab} settings: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleReindexMemory = async () => {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${base}/api/memory/index`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        setMemoryStats(data.stats)
        setSuccess(`Re-indexed ${data.chunks_indexed} chunks`)
      } else {
        setError('Failed to re-index memory')
      }
    } catch (err) {
      setError(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveConfig = async () => {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch(`${base}/api/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_dir: workspacePath,
          default_model: defaultModel,
        }),
      })

      if (res.ok) {
        setSuccess('Configuration saved')
      } else {
        setError('Failed to save configuration')
      }
    } catch (err) {
      setError(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="settings-view">
      <div className="settings-header">
        <h1>Settings</h1>
      </div>

      <div className="settings-container">
        {/* Tab Navigation */}
        <div className="settings-tabs">
          {tabs.map(tab => (
            <button
              key={tab.id}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-label">{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="settings-content">
          {loading && <div className="loading">Loading...</div>}
          {error && <div className="error">{error}</div>}
          {success && <div className="success">{success}</div>}

          {/* General Tab */}
          {activeTab === 'general' && (
            <div className="tab-pane">
              <h2>General Settings</h2>
              <div className="setting-group">
                <label>Default Model</label>
                <input
                  type="text"
                  value={defaultModel}
                  onChange={e => setDefaultModel(e.target.value)}
                  placeholder="e.g., openrouter/minimax/minimax-m2.5"
                />
              </div>
              <button onClick={handleSaveConfig} className="button-primary">
                Save Settings
              </button>
            </div>
          )}

          {/* Memory Tab */}
          {activeTab === 'memory' && (
            <div className="tab-pane">
              <h2>Memory & Search</h2>
              {memoryStats ? (
                <div className="setting-group">
                  <p>
                    <strong>Indexed Chunks:</strong> {memoryStats.chunks_indexed}
                  </p>
                  <p>
                    <strong>Embedding Model:</strong> {memoryStats.model}
                  </p>
                  <button onClick={handleReindexMemory} className="button-secondary">
                    Re-index Memory
                  </button>
                </div>
              ) : (
                <p>No memory data available</p>
              )}
            </div>
          )}

          {/* Channels Tab */}
          {activeTab === 'channels' && (
            <div className="tab-pane">
              <h2>Channel Configuration</h2>
              <div className="channel-section">
                <h3>WhatsApp</h3>
                {whatsappConfig ? (
                  <div className="setting-group">
                    <p>
                      <strong>Status:</strong>{' '}
                      <span className={whatsappConfig.configured ? 'status-active' : 'status-inactive'}>
                        {whatsappConfig.configured ? 'Configured' : 'Not Configured'}
                      </span>
                    </p>
                    {whatsappConfig.configured && whatsappConfig.phone_number_id && (
                      <p>
                        <strong>Phone ID:</strong> {whatsappConfig.phone_number_id}
                      </p>
                    )}
                    <p className="hint">
                      Configure WhatsApp credentials in the vault to enable messaging.
                    </p>
                  </div>
                ) : (
                  <p>Unable to load WhatsApp configuration</p>
                )}
              </div>
            </div>
          )}

          {/* Scheduling Tab */}
          {activeTab === 'scheduling' && (
            <div className="tab-pane">
              <h2>Scheduling</h2>
              <p className="hint">
                Manage scheduled tasks, heartbeat checks, and periodic jobs here.
              </p>
              <div className="setting-group">
                <label>Heartbeat Interval (minutes)</label>
                <input type="number" placeholder="30" defaultValue="30" />
              </div>
              <button className="button-primary">Save Schedule</button>
            </div>
          )}

          {/* Workspace Tab */}
          {activeTab === 'workspace' && (
            <div className="tab-pane">
              <h2>Workspace</h2>
              <div className="setting-group">
                <label>Workspace Directory</label>
                <input
                  type="text"
                  value={workspacePath}
                  onChange={e => setWorkspacePath(e.target.value)}
                  placeholder="~/.cato/workspace"
                  readOnly
                />
              </div>
              <p className="hint">
                This directory contains AGENTS.md, MEMORY.md, SOUL.md, and other workspace files.
              </p>
              <button onClick={handleSaveConfig} className="button-primary">
                Update Workspace
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
