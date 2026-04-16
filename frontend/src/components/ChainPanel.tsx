import { Chain, applyFix, FixResponse } from '../services/api'
import { useState } from 'react'

interface Props {
  chains: Chain[]
  selectedChain: Chain | null
  sessionId: string
  onSelectChain: (chain: Chain) => void
  onFixApplied: (fix: FixResponse) => void
}

const RISK_BG: Record<string, string> = {
  CRITICAL: 'bg-red-900/40 border-red-700 text-red-300',
  HIGH: 'bg-orange-900/40 border-orange-700 text-orange-300',
  MEDIUM: 'bg-yellow-900/40 border-yellow-700 text-yellow-300',
  LOW: 'bg-green-900/40 border-green-700 text-green-300',
}

export default function ChainPanel({ chains, selectedChain, sessionId, onSelectChain, onFixApplied }: Props) {
  const [fixing, setFixing] = useState<string | null>(null)
  const [fixError, setFixError] = useState<string | null>(null)

  const handleFix = async (chain: Chain) => {
    setFixing(chain.id)
    setFixError(null)
    try {
      const res = await applyFix(sessionId, chain.id)
      onFixApplied(res.data)
    } catch (e: any) {
      setFixError(e.response?.data?.detail || 'Fix failed')
    } finally {
      setFixing(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-lg font-semibold text-white mb-3">
        {chains.length} Chain{chains.length !== 1 ? 's' : ''} Found
      </h2>
      <div className="overflow-y-auto flex-1 space-y-2 pr-1">
        {chains.map(chain => (
          <div
            key={chain.id}
            onClick={() => onSelectChain(chain)}
            className={`border rounded-lg p-3 cursor-pointer transition-all
              ${selectedChain?.id === chain.id ? 'ring-2 ring-white' : ''}
              ${RISK_BG[chain.risk_label] ?? 'bg-slate-800 border-slate-600'}`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold uppercase tracking-wide">
                {chain.risk_label} - {(chain.risk_score * 100).toFixed(0)}%
              </span>
              <span className="text-xs text-slate-400">{chain.path.length - 1} hop{chain.path.length > 2 ? 's' : ''}</span>
            </div>
            <div className="text-xs font-mono truncate">
              {chain.path.join(' → ')}
            </div>
            <div className="text-xs text-slate-400 mt-1">
              Protected: <strong>{chain.protected_attribute}</strong>
            </div>
          </div>
        ))}
      </div>

      {/* Detail panel for selected chain */}
      {selectedChain && (
        <div className="mt-4 border-t border-slate-700 pt-4">
          <h3 className="text-sm font-semibold text-white mb-2">Chain Detail</h3>
          <div className="space-y-1 mb-3">
            {selectedChain.hops.map((hop, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-slate-300">
                <span className="font-mono bg-slate-800 px-2 py-0.5 rounded">{hop.source}</span>
                <span className="text-slate-500">→ {(hop.weight * 100).toFixed(0)}% →</span>
                <span className="font-mono bg-slate-800 px-2 py-0.5 rounded">{hop.target}</span>
              </div>
            ))}
          </div>

          {selectedChain.explanation && (
            <p className="text-xs text-slate-300 leading-relaxed bg-slate-800 p-3 rounded-lg mb-3">
              {selectedChain.explanation}
            </p>
          )}

          {selectedChain.weakest_link && (
            <div className="text-xs text-slate-400 mb-3">
              Weakest link: <code className="text-red-300">{selectedChain.weakest_link}</code>
            </div>
          )}

          {fixError && (
            <p className="text-xs text-red-400 mb-2">{fixError}</p>
          )}

          <button
            onClick={() => handleFix(selectedChain)}
            disabled={fixing === selectedChain.id}
            className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-slate-700
              disabled:text-slate-500 text-white text-sm font-semibold transition-colors"
          >
            {fixing === selectedChain.id ? 'Applying fix…' : `Cut '${selectedChain.weakest_link}'`}
          </button>
        </div>
      )}
    </div>
  )
}
