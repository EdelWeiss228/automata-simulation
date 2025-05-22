NODE_RADIUS = 20
CANVAS_SIZE = 600


class AgentNode:
    def __init__(self, canvas, x, y, name):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.name = name
        self.node_id = None
        self.text_id = None
        self.draw()

    def draw(self):
        if self.node_id:
            self.canvas.delete(self.node_id)
        if self.text_id:
            self.canvas.delete(self.text_id)
        self.node_id = self.canvas.create_oval(
            self.x - NODE_RADIUS, self.y - NODE_RADIUS,
            self.x + NODE_RADIUS, self.y + NODE_RADIUS,
            fill='lightblue'
        )
        self.text_id = self.canvas.create_text(
            self.x, self.y, text=str(self.name)
        )

    def delete(self):
        if self.node_id:
            self.canvas.delete(self.node_id)
        if self.text_id:
            self.canvas.delete(self.text_id)