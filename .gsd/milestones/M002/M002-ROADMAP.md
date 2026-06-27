# M002: Configurable AI prompts and ad integration

**Vision:** Добавить гибкую систему AI-промптов с 3 уровнями контекста: общий контекст проекта (кэшируемый через Anthropic prompt caching), настраиваемый промпт рерайта и отдельный промпт рекламной интеграции. Это позволит боту вести канал OneProvider с единой стилистикой и автоматически добавлять рекламные интеграции к постам.

## Slices

- [ ] **S01: Settings storage in DB** `risk:low` `depends:[]`
  > After this: settings хранятся и читаются из БД

- [ ] **S02: LLM layer with prompt caching** `risk:medium` `depends:[S01]`
  > After this: regenerate_text принимает system + user, кэширует контекст

- [ ] **S03: Ad integration button** `risk:low` `depends:[S02]`
  > After this: Кнопка 'Рекламный текст' работает

- [ ] **S04: Prompt settings UI** `risk:medium` `depends:[S01]`
  > After this: Настройка 3 промптов через меню

## Boundary Map

Not provided.
