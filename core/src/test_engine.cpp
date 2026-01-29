#include "engine.hpp"
#include <iostream>
#include <chrono>

int main() {
    int N = 100; // Тестируем на 100 агентах
    core_engine::Engine engine(N);

    // Инициализация случайными данными
    for (int i = 0; i < N; ++i) {
        engine.state.sensitivities[i] = 1.2f;
        for (int a = 0; a < 7; ++a) {
            engine.set_emotion(i, a, (float)(i % 7 - 3));
        }
        for (int j = 0; j < N; ++j) {
            engine.set_relation(i, j, 5.0f, 5.0f, 5.0f, 0.0f);
        }
    }

    auto start = std::chrono::high_resolution_clock::now();
    
    // 1000 шагов влияния
    for (int step = 0; step < 1000; ++step) {
        engine.influence_emotions();
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> diff = end - start;

    std::cout << "Time for 1000 steps with " << N << " agents: " << diff.count() << " s\n";
    std::cout << "Average step time: " << (diff.count() / 1000.0) * 1000.0 << " ms\n";

    return 0;
}
