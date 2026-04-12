import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BookOpen, MessageCircle, CalendarDays, Search, GitBranch,
  Sparkles, Upload, FileText, Play, ChevronDown, ChevronRight,
} from 'lucide-react'

type SectionId = 'browse' | 'chat' | 'planner' | 'pipeline'

const SECTIONS: { id: SectionId; label: string; icon: React.ReactNode }[] = [
  { id: 'browse', label: 'Browse & Search', icon: <BookOpen size={14} /> },
  { id: 'chat', label: 'Chat', icon: <MessageCircle size={14} /> },
  { id: 'planner', label: 'Planner', icon: <CalendarDays size={14} /> },
  { id: 'pipeline', label: 'Pipeline', icon: <Play size={14} /> },
]

export default function GuidePage() {
  const [active, setActive] = useState<SectionId>('browse')

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left nav */}
      <nav
        className="w-56 flex-shrink-0 border-r flex flex-col p-4 gap-1"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
        <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: 'var(--text-muted)' }}>
          User Guide
        </p>
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setActive(s.id)}
            className="flex items-center gap-2 px-3 py-2 rounded-md text-xs text-left cursor-pointer transition-colors"
            style={{
              background: active === s.id ? 'var(--bg-elevated)' : 'transparent',
              color: active === s.id ? 'var(--text-primary)' : 'var(--text-muted)',
              border: active === s.id ? '1px solid var(--border)' : '1px solid transparent',
            }}
          >
            {s.icon}
            {s.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          {active === 'browse' && <BrowseSection />}
          {active === 'chat' && <ChatSection />}
          {active === 'planner' && <PlannerSection />}
          {active === 'pipeline' && <PipelineSection />}
        </div>
      </div>
    </div>
  )
}


function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h1 className="text-xl font-bold mb-6" style={{ color: 'var(--text-primary)' }}>{children}</h1>
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold mt-8 mb-3" style={{ color: 'var(--text-primary)' }}>{children}</h2>
}

function Paragraph({ children }: { children: React.ReactNode }) {
  return <p className="text-sm leading-relaxed mb-3" style={{ color: 'var(--text-muted)' }}>{children}</p>
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex gap-2 text-xs leading-relaxed rounded-lg px-3 py-2 my-3"
      style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)', color: 'var(--phase1)' }}
    >
      <span className="font-semibold flex-shrink-0">Tip:</span>
      <span>{children}</span>
    </div>
  )
}

function Shortcut({ keys, action }: { keys: string; action: string }) {
  return (
    <div className="flex items-center gap-3 text-xs py-1">
      <kbd
        className="px-1.5 py-0.5 rounded font-mono text-xs"
        style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
      >
        {keys}
      </kbd>
      <span style={{ color: 'var(--text-muted)' }}>{action}</span>
    </div>
  )
}

function FeatureCard({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg p-4 mb-3" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-2">
        <span style={{ color: 'var(--accent)' }}>{icon}</span>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</span>
      </div>
      <div className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>{children}</div>
    </div>
  )
}

function CollapsibleDetail({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg mb-2" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-xs font-semibold cursor-pointer text-left"
        style={{ background: 'none', border: 'none', color: 'var(--text-primary)' }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {title}
      </button>
      {open && (
        <div className="px-4 pb-4 text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          {children}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Browse & Search
// ---------------------------------------------------------------------------

function BrowseSection() {
  return (
    <>
      <SectionTitle>Browse & Search</SectionTitle>
      <Paragraph>
        The <Link to="/" className="underline" style={{ color: 'var(--accent)' }}>Browse</Link> page
        is the starting point for exploring McGill's course catalogue. It shows all faculties as a
        grid of cards, each displaying the number of departments and courses available.
      </Paragraph>

      <SubHeading>Faculty and Department Navigation</SubHeading>
      <Paragraph>
        Click any faculty card to see its departments. Each department card shows the department code
        and course count. Click a department to see all its courses listed as individual cards with
        the course code, title, credits, and terms offered.
      </Paragraph>

      <SubHeading>Course Detail Pages</SubHeading>
      <Paragraph>
        Click any course to see its full detail page, which includes the description, credit count,
        terms offered, raw prerequisites text, restrictions, and notes. If the course has
        prerequisites or corequisites, they appear as clickable links so you can trace the chain.
      </Paragraph>

      <FeatureCard icon={<GitBranch size={14} />} title="Prerequisite Graph">
        <p>
          Below the course details, a D3 force-directed graph visualizes the full prerequisite chain.
          Red arrows indicate prerequisites and blue dashed arrows indicate corequisites.
          Nodes are draggable and clickable — click any node to navigate to that course.
        </p>
      </FeatureCard>

      <SubHeading>Search</SubHeading>
      <Paragraph>
        The search bar on the Browse page accepts natural-language queries. When you submit a search,
        it redirects to the <Link to="/chat" className="underline" style={{ color: 'var(--accent)' }}>Chat</Link> page
        with your query pre-filled, so the AI advisor can answer using the full retrieval pipeline.
      </Paragraph>

      <Tip>
        You can search for anything from specific course codes ("COMP 250") to broad questions
        ("what statistics courses are available for arts students?").
      </Tip>
    </>
  )
}


// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

function ChatSection() {
  return (
    <>
      <SectionTitle>Chat</SectionTitle>
      <Paragraph>
        The <Link to="/chat" className="underline" style={{ color: 'var(--accent)' }}>Chat</Link> page
        is an AI-powered course advisor. Ask questions in plain English and get answers grounded in
        McGill's actual course data — descriptions, prerequisites, program requirements, department
        resources, and academic calendar information.
      </Paragraph>

      <SubHeading>How It Works</SubHeading>
      <Paragraph>
        When you send a message, the system runs a multi-step retrieval pipeline behind the scenes:
      </Paragraph>
      <div className="space-y-2 mb-4">
        <FeatureCard icon={<Search size={14} />} title="Keyword Search">
          <p>Full-text search across all course titles and descriptions.</p>
        </FeatureCard>
        <FeatureCard icon={<Sparkles size={14} />} title="Semantic Search">
          <p>
            Embeds your query into a vector and finds the most semantically similar course chunks and
            program pages. This is how the system finds relevant results even when you don't use the
            exact words from the catalogue.
          </p>
        </FeatureCard>
        <FeatureCard icon={<GitBranch size={14} />} title="Graph Traversal">
          <p>
            If your query mentions a course code (e.g. "COMP 250"), the system queries the Neo4j
            prerequisite graph to pull in prerequisite and corequisite relationships.
          </p>
        </FeatureCard>
        <FeatureCard icon={<FileText size={14} />} title="Structured SQL">
          <p>
            For data questions ("how many courses does the math department offer?"), the system
            generates a SQL query against the course database and returns precise counts and
            aggregations.
          </p>
        </FeatureCard>
      </div>
      <Paragraph>
        Results from all four sources are fused together using reciprocal rank fusion, then passed to
        Claude as context for generating the final answer.
      </Paragraph>

      <SubHeading>Sidebar</SubHeading>
      <Paragraph>
        The left sidebar shows three things: the current retrieval pipeline phases (so you can see
        what's running), the source courses referenced in the last answer, and the system health
        status for PostgreSQL and Neo4j.
      </Paragraph>

      <SubHeading>Example Queries</SubHeading>
      <div className="rounded-lg p-4 space-y-2 text-xs" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
        <p>"What are the prerequisites for COMP 302?"</p>
        <p>"Which 3-credit psychology courses are offered in the fall?"</p>
        <p>"Compare MATH 240 and MATH 235"</p>
        <p>"What courses should a first-year computer science student take?"</p>
        <p>"When is the add/drop deadline?"</p>
        <p>"How many courses does the biology department have?"</p>
      </div>

      <Shortcut keys="Enter" action="Send message" />
      <Shortcut keys="Shift + Enter" action="New line within the input" />
    </>
  )
}


// ---------------------------------------------------------------------------
// Planner
// ---------------------------------------------------------------------------

function PlannerSection() {
  return (
    <>
      <SectionTitle>Planner</SectionTitle>
      <Paragraph>
        The <Link to="/planner" className="underline" style={{ color: 'var(--accent)' }}>Planner</Link> is
        a full curriculum planning tool for building semester-by-semester course schedules. It combines
        manual course selection with AI-powered analysis and a plan-scoped advisor chat. The layout
        has three columns: a plan list on the left, the plan detail in the center, and an AI advisor
        chat on the right.
      </Paragraph>

      <SubHeading>Creating a Plan</SubHeading>
      <Paragraph>
        Click the <strong style={{ color: 'var(--text-primary)' }}>+</strong> button in the plan list
        sidebar to open the new plan form. The form has four fields:
      </Paragraph>
      <div className="space-y-2 mb-4">
        <CollapsibleDetail title="Faculty & Program">
          <p className="mb-2">
            Select a faculty from the dropdown to see its available programs. Choosing a program
            pre-populates the plan with required courses distributed across semesters, respecting
            Fall/Winter scheduling and credit balance. The plan title auto-fills from the program name
            if you haven't typed one.
          </p>
          <p>
            These dropdowns are optional — you can create a blank plan and add courses manually.
          </p>
        </CollapsibleDetail>
        <CollapsibleDetail title="Start Term">
          <p>
            Pick a season (Fall or Winter) and year. This determines how semesters are labeled and
            helps the AI advisor reason about term availability when courses are only offered in
            specific semesters.
          </p>
        </CollapsibleDetail>
        <CollapsibleDetail title="Plan Title">
          <p>
            A name for your plan (e.g. "B.Sc. Computer Science Year 1"). If you selected a program
            above, this auto-fills but can be edited.
          </p>
        </CollapsibleDetail>
        <CollapsibleDetail title="Interests">
          <p>
            Comma-separated topics (e.g. "machine learning, statistics, data science"). These are
            passed to the AI advisor and plan generator so recommendations align with what you're
            interested in.
          </p>
        </CollapsibleDetail>
      </div>

      <SubHeading>Managing Semesters</SubHeading>
      <Paragraph>
        The center panel shows your semesters as a vertical list of cards. Each card has the
        term name (e.g. "Fall 2026"), a credit total, and the courses assigned to it.
      </Paragraph>
      <div className="rounded-lg p-4 mb-4 space-y-3 text-xs" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Add a semester:</strong>{' '}
          Type a term name (e.g. "Fall 2026") into the input at the bottom and click "Add Semester"
          or press Enter.
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Remove a semester:</strong>{' '}
          Click the trash icon on the semester card header. This removes the semester and all its
          courses from the plan.
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Add a course:</strong>{' '}
          Click "+ Add Course" inside any semester card. An inline input appears — type a course code
          (e.g. "COMP 250") and press Enter. The code is auto-uppercased and the system fetches the
          full course details (title, credits, terms) to display alongside it.
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Remove a course:</strong>{' '}
          Hover over a course row and click the X icon that appears on the right.
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>View course details:</strong>{' '}
          Each course code is a link — click it to navigate to the full course detail page with
          description, prerequisites, and the prerequisite graph.
        </div>
      </div>

      <SubHeading>Document Uploads</SubHeading>
      <Paragraph>
        Click the "Documents" toggle below the plan header to expand the document drawer.
        Upload transcripts, AP score reports, course guides, or any other files relevant to your
        planning. Accepted formats: PDF, TXT, CSV, XLSX.
      </Paragraph>
      <Paragraph>
        Uploaded documents are attached to the plan and available to the AI advisor, so you can
        ask questions like "based on my transcript, which prerequisites have I completed?" or
        "do my AP scores qualify for any exemptions?"
      </Paragraph>

      <SubHeading>AI Plan Generation</SubHeading>
      <FeatureCard icon={<Sparkles size={14} />} title="Explain Plan">
        <p className="mb-2">
          The "Explain Plan" button in the plan header triggers a comprehensive AI analysis of your
          current semester layout. Claude examines your courses, prerequisites, term availability,
          credit balance, and your stated interests to produce a detailed markdown explanation that
          covers:
        </p>
        <ul className="list-disc pl-4 space-y-1">
          <li>The big picture — what the plan accomplishes and how semesters build on each other</li>
          <li>Course-by-course rationale — why each course is placed where it is</li>
          <li>Workload and strategy notes — which semesters are heavier, what pairs well</li>
          <li>Prerequisite chains — how dependencies flow across semesters</li>
          <li>Alternatives — backup options for elective slots</li>
        </ul>
        <p className="mt-2">
          After the first generation, the button changes to "Regenerate" so you can get a fresh
          analysis after making changes.
        </p>
      </FeatureCard>

      <SubHeading>Plan-Scoped Advisor Chat</SubHeading>
      <Paragraph>
        When a plan is selected, a chat panel appears on the right side of the screen. This is a
        dedicated AI advisor that knows your plan — its courses, semesters, documents, and your
        interests. It opens with a welcome message: "I'm your advisor for [plan title]."
      </Paragraph>
      <div className="rounded-lg p-4 mb-4 space-y-3 text-xs" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Resizable:</strong>{' '}
          Drag the left border of the chat panel to resize it (280px to 800px). Useful when you want
          to read longer responses without scrolling.
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Contextual:</strong>{' '}
          Unlike the global Chat page, this advisor sees your plan details. Ask it things like
          "is my credit load too heavy in semester 2?" or "what elective should I add to fill the
          gap in Winter?"
        </div>
        <div>
          <strong style={{ color: 'var(--text-primary)' }}>Separate session:</strong>{' '}
          Each plan gets its own chat session, so switching between plans gives you a fresh
          conversation scoped to that plan.
        </div>
      </div>
      <Paragraph>
        The advisor uses the same multi-source retrieval pipeline as the global chat (keyword,
        semantic, graph, SQL) but additionally receives your plan context — semesters, courses,
        uploaded documents — so its answers are specific to your situation.
      </Paragraph>

      <SubHeading>Plan Status</SubHeading>
      <Paragraph>
        Each plan has a status that you can change via the dropdown in the plan header:
      </Paragraph>
      <div className="rounded-lg p-4 mb-4 space-y-2 text-xs" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
        <div><strong style={{ color: 'var(--text-primary)' }}>Draft</strong> — work in progress, the default for new plans.</div>
        <div><strong style={{ color: 'var(--text-primary)' }}>Active</strong> — the plan you're currently following.</div>
        <div><strong style={{ color: 'var(--text-primary)' }}>Archived</strong> — plans you've finished or abandoned. Kept for reference.</div>
      </div>

      <SubHeading>Quick Reference</SubHeading>
      <Shortcut keys="Enter" action="Submit new semester or course" />
      <Shortcut keys="Escape" action="Cancel inline course input" />
    </>
  )
}


// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

function PipelineSection() {
  return (
    <>
      <SectionTitle>Pipeline</SectionTitle>
      <Paragraph>
        The data pipeline scrapes McGill's course catalogue, resolves prerequisites into a graph,
        and generates vector embeddings for search. You'll find a "Run Pipeline" button on
        faculty and department pages.
      </Paragraph>

      <SubHeading>Pipeline Phases</SubHeading>
      <div className="space-y-2 mb-4">
        <FeatureCard icon={<span className="text-xs font-bold" style={{ color: 'var(--phase1)' }}>1</span>} title="Pre-check">
          <p>
            Scans the database to see which departments already have embeddings. Departments that
            are already processed get skipped unless you check "Force re-process."
          </p>
        </FeatureCard>
        <FeatureCard icon={<span className="text-xs font-bold" style={{ color: 'var(--phase2)' }}>2</span>} title="Scrape">
          <p>
            Fetches course pages from the McGill Course Catalogue, extracts metadata (title,
            credits, terms, description, prerequisites, restrictions), and saves to the database.
            Also scrapes program guide pages, external advising pages, and general university info
            (academic calendar, important dates).
          </p>
        </FeatureCard>
        <FeatureCard icon={<span className="text-xs font-bold" style={{ color: 'var(--phase3)' }}>3</span>} title="Resolve">
          <p>
            Parses prerequisite and corequisite text using Jaro-Winkler string matching to identify
            course references, then builds a Neo4j graph with Course, Department, Faculty, and Term
            nodes connected by prerequisite, corequisite, and membership relationships.
          </p>
        </FeatureCard>
        <FeatureCard icon={<span className="text-xs font-bold" style={{ color: 'var(--phase4)' }}>4</span>} title="Embed">
          <p>
            Chunks course descriptions and program pages into overlapping sentence windows, embeds
            them with Voyage AI, and stores the vectors in pgvector for semantic search.
          </p>
        </FeatureCard>
      </div>

      <SubHeading>Running the Pipeline</SubHeading>
      <Paragraph>
        Navigate to any faculty or department page and click the "Run Pipeline" button. Progress
        updates stream in real-time via SSE — you'll see each phase transition from idle to running
        to done. When complete, a summary shows courses scraped, entities created, and chunks
        embedded.
      </Paragraph>

      <Tip>
        Check "Force re-process" to re-scrape and re-embed departments that already have data.
        This is useful after the catalogue is updated at the start of a new term.
      </Tip>

      <SubHeading>Scope</SubHeading>
      <Paragraph>
        The pipeline is scoped to whatever page you're on — running it from a faculty page processes
        all departments in that faculty, while running it from a department page processes just that
        department. General university info pages (academic calendar, important dates, student
        services) are always included regardless of scope.
      </Paragraph>
    </>
  )
}
