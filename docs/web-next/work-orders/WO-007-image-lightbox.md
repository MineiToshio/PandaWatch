# WO-007: Image Lightbox

**Phase:** 3  
**Effort:** S  
**Status:** Done  
**Related:** [FRD-005](../FRD-005-item-detail.md), [WO-006](WO-006-item-detail.md)  
**Prerequisites:** WO-006 (ImageCarousel exists)

---

## Objective

Al hacer clic en la imagen principal del `ImageCarousel` se abre un modal/lightbox
de pantalla completa que muestra la imagen a mayor tamaño con navegación propia
(flechas, dots, teclado). Cierra con Escape, clic en el fondo, o botón ✕.

---

## Scope

Un solo archivo cambia: `components/item/ImageCarousel.tsx`.  
No se toca `page.tsx` ni ningún otro componente — el lightbox es interno al carrusel.

---

## Diseño

### Trigger

- `cursor: zoom-in` en el contenedor de la imagen del carrusel.
- Clic en la imagen (no en las flechas de navegación — esas tienen `e.stopPropagation()`).

### Overlay

```
position: fixed; inset: 0; z-index: 9999;
background: rgba(0,0,0,0.92);
display: flex; align-items: center; justify-content: center;
```

Clic en el fondo cierra el lightbox.

### Imagen en el modal

```css
display: block;
max-width: 90vw;
max-height: 75vh;
width: auto;
height: auto;
border-radius: 6px;
```

Usando `<img>` (no `next/image`) para ambas fuentes (local `/images/` y remota),
igual que el fallback actual del carrusel. Así la imagen se muestra a su tamaño
natural hasta los límites del viewport — no se estira si es pequeña, no supera
los límites si es grande.

### Controles en el lightbox

| Control | Posición |
|---|---|
| Botón ✕ | `position: fixed` top-right del overlay |
| Flechas ‹ › | Posicionadas a los lados del bloque imagen (±20px fuera) |
| Kind badge | `position: absolute` bottom-left sobre la imagen |
| Contador N / total | `position: absolute` bottom-right sobre la imagen |
| Descripción | Bajo la imagen, texto blanco semitransparente |
| Dots (2–8 imgs) | Bajo la descripción |

### Teclado

| Tecla | Acción |
|---|---|
| `Escape` | Cierra lightbox |
| `←` | Imagen anterior (preventDefault cuando lightbox abierto) |
| `→` | Imagen siguiente (preventDefault cuando lightbox abierto) |

### Scroll lock

Cuando el lightbox está abierto: `document.body.style.overflow = 'hidden'`.  
Se restaura al cerrar (`useEffect` con cleanup).

### Estado compartido

`idx` y `src` son estados del componente padre (`ImageCarousel`), compartidos
entre el carrusel thumbnail y el lightbox. No hace falta estado extra salvo
`lightboxOpen: boolean`.

---

## Acceptance Criteria

- [x] Clic en imagen (no en flecha) abre el lightbox
- [x] La imagen se ve grande, sin pixelación artificial
- [x] Flechas, dots y teclado navegan dentro del lightbox
- [x] Escape + clic en fondo + botón ✕ cierran el lightbox
- [x] Scroll de la página bloqueado mientras el lightbox está abierto
- [x] 0 errores TypeScript

---

## Implementation Notes

- El kind badge en el lightbox va en la esquina inferior-izquierda (distinto del
  thumbnail donde va arriba-izquierda) para no tapar la imagen.
- Las flechas se posicionan con `position: absolute` en un wrapper `position: relative`
  sobre el bloque de imagen, con `left: -48px` / `right: -48px` para quedar fuera
  del recuadro de la imagen pero dentro del overlay.
- El botón ✕ usa `position: fixed` (no `absolute`) para que siempre esté en la
  esquina independientemente del tamaño del contenido.
- El `useEffect` del teclado ya existía; se amplia para incluir Escape y añadir
  `lightboxOpen` a las dependencias.
