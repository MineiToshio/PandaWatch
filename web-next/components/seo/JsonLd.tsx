/**
 * Serializes schema.org structured data into a <script type="application/ld+json">.
 * Server component. Escapes `<` to prevent breaking out of the script context.
 */
export function JsonLd({ data }: { data: object | object[] }) {
  const json = JSON.stringify(data).replace(/</g, '\\u003c')
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />
}

export default JsonLd
