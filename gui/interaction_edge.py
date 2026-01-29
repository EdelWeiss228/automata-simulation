class InteractionEdge:
    def __init__(self, canvas, node_from, node_to, success_value):
        self.canvas = canvas
        self.node_from = node_from
        self.node_to = node_to
        # Приводим к строке и очищаем, чтобы исключить ошибки типов
        self.success = str(success_value).lower().strip()
        self.line_id = None
        self.text_id = None
        self.arrow_id = None
        self.draw()

    def draw(self):
        if self.line_id: self.canvas.delete(self.line_id)
        if self.text_id: self.canvas.delete(self.text_id)
        if self.arrow_id: self.canvas.delete(self.arrow_id)

        from_x, from_y = self.node_from.x, self.node_from.y
        to_x, to_y = self.node_to.x, self.node_to.y
        mid_x = (from_x + to_x) / 2
        mid_y = (from_y + to_y) / 2

        dx = to_x - from_x
        dy = to_y - from_y
        length = (dx**2 + dy**2)**0.5 if (dx != 0 or dy != 0) else 1.0
        offset = 30
        nx = -dy / length * offset
        ny = dx / length * offset
        ctrl_x = mid_x + nx
        ctrl_y = mid_y + ny

        # Определяем стиль
        if self.success in ["success", "true"]:
            color, text, dash = 'green', "Успешно", None
        elif self.success == "refusal":
            color, text, dash = 'black', "Отказ", (5, 3)
        elif self.success in ["fail", "false"]:
            color, text, dash = 'red', "Неудачно", None
        else:
            # Отладочный режим: если пришло что-то странное
            color, text, dash = 'magenta', f"Err: {self.success}", (2, 2)

        # 1. Линия
        self.line_id = self.canvas.create_line(
            from_x, from_y, ctrl_x, ctrl_y, to_x, to_y,
            smooth=True, width=2, fill=color, dash=dash
        )

        # 2. Стрелка
        arrow_size = 6
        ux, uy = (to_x - ctrl_x) / length, (to_y - ctrl_y) / length
        ax, ay = to_x - ux * 5, to_y - uy * 5
        px, py = -uy, ux
        points = [ax + px * arrow_size, ay + py * arrow_size,
                  ax - px * arrow_size, ay - py * arrow_size, to_x, to_y]
        self.arrow_id = self.canvas.create_polygon(points, fill=color, outline=color)

        # 3. Текст
        self.text_id = self.canvas.create_text(
            mid_x + nx*1.2, mid_y + ny*1.2, # Чуть смещаем текст от дуги
            text=text, fill=color, font=('Arial', 9, 'bold')
        )

    def delete(self):
        if self.line_id: self.canvas.delete(self.line_id)
        if self.text_id: self.canvas.delete(self.text_id)
        if self.arrow_id: self.canvas.delete(self.arrow_id)