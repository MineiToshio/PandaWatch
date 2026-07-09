import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// @testing-library/react no limpia el DOM entre tests por sí solo fuera de
// Jest — sin esto, los tests de __tests__/components/** acumulan nodos entre
// `it()` del mismo archivo y getByRole/getByText empiezan a matchear
// múltiples elementos (auditoría #20, primeros tests de componentes del repo).
afterEach(() => {
  cleanup()
})
