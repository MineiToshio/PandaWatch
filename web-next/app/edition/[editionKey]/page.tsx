type Props = {
  params: Promise<{ editionKey: string }>
}

export default async function EditionPage({ params }: Props) {
  const { editionKey } = await params
  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <p style={{ color: 'var(--text-secondary)' }}>
        Edition: {editionKey} — coming soon (WO-006)
      </p>
    </main>
  )
}
