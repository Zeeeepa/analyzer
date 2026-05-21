# Using NPX Claude Flow based systems
!! use npx when you want to use claude flow as a resarch, sparc or coding tool
!! use npm when you want it to be part of a software application

!! run npx in a seperate terminal from claude code because sometimes claude code avoids using it (although that may change now that claude code itself can spawn multiple agents)

!! assuming npx claude-flow and npx 

Instead of installing npm globally.
Can use NPX to run the latest versions of claude-flow etc

- npx research-swarm init - Initialize SQLite database (run first, i think only needs to be run once?)
  - npx research-swarm research <agent> <task> - Run single research task
  - npx research-swarm swarm <tasks...> - Run parallel research swarm
  - npx research-swarm goal-research <goal> - GOAP-based goal research
  - npx research-swarm list - List research jobs
  - npx research-swarm stats - Show learning statistics


  | --swarm-size <number>        | 5        | Number of swarm agents (3-7)          |
  | --max-concurrent <number>    | 4        | Max concurrent agents running         |
  | -t, --time <minutes>         | 120      | Time budget in minutes                |
  | -d, --depth <number>         | 5        | Research depth (1-10)                 |
  | -f, --focus <mode>           | balanced | Focus: narrow, balanced, or broad     |
  | --anti-hallucination <level> | high     | Anti-hallucination: low, medium, high |
  | --verbose                    | -        | Verbose output from agents            |
  | --single-agent               | -        | Use single-agent mode (legacy)        |
  | --no-citations               | -        | Disable citation requirements         |
  | --no-ed2551                  | -        | Disable ED2551 enhanced mode          |


  Example - Maximum Configuration:
  npx research-swarm research researcher "Analyze quantum computing market trends 2025" \
    --swarm-size 7 \
    --max-concurrent 6 \
    --time 240 \
    --depth 10 \
    --focus broad \
    --anti-hallucination high \
    --verbose

    npx research-swarm goal-research <goal> [options]

  Options:

  | Option                    | Default | Description                 |
  |---------------------------|---------|-----------------------------|
  | --swarm-size <number>     | 5       | Base swarm size (3-7)       |
  | --max-concurrent <number> | 3       | Max concurrent agents       |
  | -t, --time <minutes>      | 120     | Total time budget           |
  | -d, --depth <number>      | 5       | Research depth per sub-goal |
  | --verbose                 | -       | Verbose output              |

  Example - Complex Goal with Max Agents:
  npx research-swarm goal-research \
    "Comprehensive analysis of emerging AI hardware startups with revenue > $10M" \
    --swarm-size 7 \
    --max-concurrent 5 \
    --time 300 \
    --depth 9 \
    --verbose

