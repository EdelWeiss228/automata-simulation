class Player:
    def __init__(self, name, group):
        self.name = name
        self.group = group
        self.emotions = ['joy_sadness', 'anger_humility', 'fear_calm', 'love_alienation', 'disgust_acceptance', 'shame_confidence', 'surprise_habit']
        self.current_emotion = 'joy_sadness'  
        self.emotion_value = 0
        self.relations = {}  
        
    def choose_emotion(self):
        print("Выберите эмоцию для игрока:")
        for i, emotion in enumerate(self.emotions, 1):
            print(f"{i}. {emotion}")
        
        choice = int(input(f"Выберите номер эмоции (1-{len(self.emotions)}): "))
        if 1 <= choice <= len(self.emotions):
            self.current_emotion = self.emotions[choice - 1]
            print(f"Эмоция игрока установлена на: {self.current_emotion}")
            
            while True:
                try:
                    self.emotion_value = int(input("Введите силу эмоции (-3 до 3): "))
                    if -3 <= self.emotion_value <= 3:
                        break
                    else:
                        print("Введите число от -3 до 3.")
                except ValueError:
                    print("Некорректный ввод. Введите целое число.")
        else:
            print("Некорректный выбор. Попробуйте снова.")
    
    def choose_interaction(self, agents_dict):
        print("Игрок может взаимодействовать с агентами, которые к нему подошли на основе их отношений.")
        approached_agents = list(agents_dict.keys())
        
        if approached_agents:
            print("Игрок может взаимодействовать с следующими агентами:")
            for i, agent_name in enumerate(approached_agents, 1):
                print(f"{i}. {agent_name}")
            
            choice = int(input(f"Выберите номер агента (1-{len(approached_agents)}): "))
            if 1 <= choice <= len(approached_agents):
                target_agent_name = approached_agents[choice - 1]
                target_agent = agents_dict.get(target_agent_name)
                
                emotion_name, emotion_value = target_agent.get_primary_emotion()
                print(f"{target_agent.name} выбирает взаимодействие с вами. Его примарная эмоция: {emotion_name} с силой {emotion_value}.")
                
                self.choose_emotion()
                self.interact_with_agent(target_agent)
            else:
                print("Некорректный выбор. Попробуйте снова.")
        else:
            print("Нет агентов, которые подошли для взаимодействия.")
    
    def interact_with_agent(self, target_agent):
        emotion_value = self.emotion_value
        print(f"{self.name} взаимодействует с {target_agent.name} в эмоции {self.current_emotion} с величиной {emotion_value}.")
        
        target_agent.automaton.adjust_emotion(self.current_emotion, emotion_value)
        target_agent.relations[self.name]['affinity'] += emotion_value
        target_agent.relations[self.name]['trust'] += emotion_value
        target_agent.relations[self.name]['utility'] += emotion_value
        
        print(f"Отношения с {target_agent.name} обновлены!")
    
    def get_primary_emotion(self):
        return self.current_emotion, self.emotion_value

    def respond_to_agent(self, agent_name, emotion_name, emotion_value):
        print(f"{self.name} отвечает на эмоцию {emotion_name} с силой {emotion_value} агента {agent_name}.")
        
        response_value = emotion_value
        
        if agent_name in self.relations:
            self.relations[agent_name]['affinity'] += response_value
            self.relations[agent_name]['trust'] += response_value
            self.relations[agent_name]['utility'] += response_value
            print(f"Отношения с {agent_name} обновлены на основе ответа игрока!")
        else:
            print(f"Неизвестный агент: {agent_name}. Отношения не обновлены.")