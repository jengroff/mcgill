import Sidebar from '../components/Sidebar'
import ChatPanel from '../components/ChatPanel'

export default function ChatPage() {
  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatPanel />
      </main>
    </div>
  )
}
