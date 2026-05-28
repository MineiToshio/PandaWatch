type Props = {
  params: Promise<{ slug: string }>
}

export default async function ItemPage({ params }: Props) {
  const { slug } = await params
  return (
    <main className="max-w-7xl mx-auto px-4 py-8">
      <p style={{ color: 'var(--text-secondary)' }}>
        Item: {slug} — coming soon (WO-007)
      </p>
    </main>
  )
}
