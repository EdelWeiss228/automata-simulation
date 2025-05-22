class InteractionEdge:
    def __init__(self, canvas, node_from, node_to, success):
        self.canvas = canvas
        self.node_from = node_from
        self.node_to = node_to
        self.success = success
        self.line_id = None
        self.text_id = None
        self.arrow_id = None
        self.draw()

    def draw(self):
        if self.line_id:
            self.canvas.delete(self.line_id)
        if self.text_id:
            self.canvas.delete(self.text_id)
        if self.arrow_id:
            self.canvas.delete(self.arrow_id)

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

        if self.success == "success":
            color = 'green'
            text = "Успешно"
            text_color = 'green'
            # Полная дуга
            self.line_id = self.canvas.create_line(
                from_x, from_y,
                ctrl_x, ctrl_y,
                to_x, to_y,
                smooth=True,
                width=2,
                fill=color
            )
            # Добавим стрелку
            arrow_size = 6
            arrow_dx = to_x - ctrl_x
            arrow_dy = to_y - ctrl_y
            arrow_len = (arrow_dx ** 2 + arrow_dy ** 2) ** 0.5 or 1.0
            ux = arrow_dx / arrow_len
            uy = arrow_dy / arrow_len
            # Точка ближе к целевому узлу
            ax = to_x - ux * 5
            ay = to_y - uy * 5
            # Перпендикуляр
            px = -uy
            py = ux
            points = [
                ax + px * arrow_size, ay + py * arrow_size,
                ax - px * arrow_size, ay - py * arrow_size,
                to_x, to_y
            ]
            self.arrow_id = self.canvas.create_polygon(points, fill=color, outline=color)
        elif self.success == "refusal":
            color = 'black'
            text = "Отказ"
            text_color = 'black'
            # Полная дуга, но пунктирная линия
            self.line_id = self.canvas.create_line(
                from_x, from_y,
                ctrl_x, ctrl_y,
                to_x, to_y,
                smooth=True,
                width=2,
                fill=color,
                dash=(5, 3)
            )
            # Добавим стрелку
            arrow_size = 6
            arrow_dx = to_x - ctrl_x
            arrow_dy = to_y - ctrl_y
            arrow_len = (arrow_dx ** 2 + arrow_dy ** 2) ** 0.5 or 1.0
            ux = arrow_dx / arrow_len
            uy = arrow_dy / arrow_len
            # Точка ближе к целевому узлу
            ax = to_x - ux * 5
            ay = to_y - uy * 5
            # Перпендикуляр
            px = -uy
            py = ux
            points = [
                ax + px * arrow_size, ay + py * arrow_size,
                ax - px * arrow_size, ay - py * arrow_size,
                to_x, to_y
            ]
            self.arrow_id = self.canvas.create_polygon(points, fill=color, outline=color)
        else:
            color = 'red'
            text = "Неудачно"
            text_color = 'red'
            # Полная дуга
            self.line_id = self.canvas.create_line(
                from_x, from_y,
                ctrl_x, ctrl_y,
                to_x, to_y,
                smooth=True,
                width=2,
                fill=color
            )
            # Добавим стрелку
            arrow_size = 6
            arrow_dx = to_x - ctrl_x
            arrow_dy = to_y - ctrl_y
            arrow_len = (arrow_dx ** 2 + arrow_dy ** 2) ** 0.5 or 1.0
            ux = arrow_dx / arrow_len
            uy = arrow_dy / arrow_len
            # Точка ближе к целевому узлу
            ax = to_x - ux * 5
            ay = to_y - uy * 5
            # Перпендикуляр
            px = -uy
            py = ux
            points = [
                ax + px * arrow_size, ay + py * arrow_size,
                ax - px * arrow_size, ay - py * arrow_size,
                to_x, to_y
            ]
            self.arrow_id = self.canvas.create_polygon(points, fill=color, outline=color)

        # Текст ближе к центру дуги (на средней точке)
        text_x = (from_x + to_x) / 2
        text_y = (from_y + to_y) / 2 - 10

        self.text_id = self.canvas.create_text(
            text_x, text_y,
            text=text,
            fill=text_color,
            font=('Arial', 10, 'bold')
        )

    def delete(self):
        if self.line_id:
            self.canvas.delete(self.line_id)
        if self.text_id:
            self.canvas.delete(self.text_id)
        if self.arrow_id:
            self.canvas.delete(self.arrow_id)