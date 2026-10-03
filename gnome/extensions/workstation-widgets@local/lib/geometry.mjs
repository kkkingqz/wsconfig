export function placePopup(button, area, surface, gap = 8, gutter = 0) {
    const width = Math.min(surface.width, area.width);
    const height = Math.min(surface.height, area.height);
    return {x: Math.round(Math.max(area.x, Math.min(button.x + button.width - width + gutter, area.x + area.width - width))),
        y: Math.round(Math.max(area.y, Math.min(button.y + button.height + gap - gutter, area.y + area.height - height))),
        width: Math.floor(width), height: Math.floor(height)};
}
