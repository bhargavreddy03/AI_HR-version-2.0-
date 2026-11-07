export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <div className="max-w-2xl space-y-6 rounded-xl border border-slate-200 bg-white p-10 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300">
          Step 3.1 Initialized
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
          AI HR Intelligence Platform
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Enterprise Modular Monolith Foundation (Next.js 14 + FastAPI + PostgreSQL 16 + Redis)
        </p>
        <div className="grid grid-cols-2 gap-4 text-left text-xs text-slate-500 dark:text-slate-400">
          <div className="rounded-lg border border-slate-100 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Frontend Core:</span>
            <p className="mt-1">Next.js 14 App Router, TypeScript, Tailwind CSS</p>
          </div>
          <div className="rounded-lg border border-slate-100 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Backend API:</span>
            <p className="mt-1">Python FastAPI, Pydantic v2, SQLAlchemy 2.0</p>
          </div>
        </div>
      </div>
    </main>
  );
}
