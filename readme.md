# Cookie.Fun + Twitter Analysis Tool

A CLI tool built for the February 2025 cookie.fun hackathon. This tool ingests data on web3 AI agents from [cookie.fun](https://cookie.fun) using its DataSwarm API and tweets from Twitter (X), then runs advanced reasoning models to generate market analyses based on user-supplied prompts.

Its main feature is being able to efficiently process much more source data than the reasoning model would normally be able to handle. In order to achieve that, the vast set of input data is chunked into smaller batches, processed, and then recursively recombined and reprocessed until we are left with one final result.

## Overview

This tool brings together data from two sources:
- **cookie.fun**: Provides data about AI agents and projects in the web3 space.
- **Twitter (X)**: Offers social media data to help you evaluate market sentiment and community engagement.

By combining these data streams, the tool enables users to generate detailed, markdown-formatted analyses covering topics such as market trends, social engagement, and project evaluations.

## Features

- **Data Ingestion**:
  - Ingest agent data from cookie.fun.
  - Ingest tweets (and optionally replies) for given Twitter usernames.
- **Data Analysis**:
  - Run custom analysis pipelines using reasoning models.
  - Support for agent-specific and aggregated tweet analysis.
- **Prompt-Driven Analysis**:
  - Leverage pre-made or custom analysis prompts (with optional YAML frontmatter filters).
- **Flexible Output**:
  - Generate markdown-formatted summaries and evaluations.
- **Storage**:
  - Saves results to SQLite databases for future reference.

## Installation & Setup

### Prerequisites

- Python 3.12 or higher.
- A virtual environment (via `venv` or `conda`) is recommended.

### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/cookie-fun-twitter-analysis.git
   cd cookie-fun-twitter-analysis
   ```

2. **Set Up Your Virtual Environment**
   ```bash
   # Using venv
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install the Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup Environment Variables & Twitter Cookies**

   - Create a `.env` file in the project root:
     ```dotenv
     OPENAI_API_KEY=sk-XXXXX
     COOKIE_FUN_API_KEY=YYYYY

     TWITTER_COOKIES_FILE=twitter.cookies.json
     ```

   - (Optional) Provide your Twitter authentication cookies by creating `twitter.cookies.json`:
     ```json
     {
         "auth_token": "XXXX",
         "ct0": "YYYY"
     }
     ```

5. **Customize Analysis Prompts**
   - Edit or add prompt files in the `prompts/` directory. For example:
     ```txt
     filter: large_caps
     ---
     Find large-cap projects that are interesting to investors. Look out for high mind share, high social engagement, and stable growth.
     ```

## Configuration

The project relies on a few configuration files:
- **`.env` file**: For API keys.
- **`twitter.cookies.json`**: Required for Twitter data ingestion.
- **`prompts/*.txt`**: Contains analysis prompts, optionally with YAML frontmatter to filter the dataset (e.g., `small_caps`, `large_caps`, etc.).

## Usage

The tool is run via the command line with multiple subcommands. Here are some examples:

### Cookie.fun Ingestion

Ingest data from the cookie.fun API:
```bash
$ python . ingest:cookie.fun --delta-interval _3Days
```
This command will output a list of agents with details like name, price, market cap, and associated Twitter handles.

### Twitter Ingestion

Ingest tweets from a specific Twitter user:
```bash
$ python . ingest:twitter your_username --count 50 --replies
```
This command retrieves tweets (and optionally replies) for the specified username.

### Data Analysis

Run an analysis on ingested cookie.fun data using a prompt:
```bash
$ python . analyze ./prompts/large_caps.txt --run-id 17
```
This command loads the prompt file, selects an ingestion run (either by ID or the latest), and processes the analysis pipeline. The output is a markdown report summarizing the data insights.

### Tweet Summarization

Summarize tweets for one or more Twitter users:
```bash
$ python . summarize:tweets user1 user2 --focus-ai
```
The tool fetches tweets for the provided usernames and generates a detailed summary that can optionally focus on AI-related trends.

### Agent Tweets Analysis

Analyze recent tweets for a specific agent:
```bash
$ python . analyze:agent_tweets your_username --context ./path/to/context.txt --count 20
```
This command evaluates the quality and consistency of an agent’s tweets and produces an in-depth markdown analysis.

## Prompts & Customization

The analysis prompts are stored as text files in the `prompts/` folder. Each prompt may start with an optional YAML frontmatter that determines how the data is filtered before analysis. Supported filters include:

- **unfiltered**: Process all agents (may be slow and expensive).
- **small_caps**: Only agents with a market cap < $10M.
- **large_caps**: Only agents with a market cap > $100M.
- **resilient**: Agents with a market cap delta (over 3 or 7 days) >= -10%.

Feel free to create your own prompts to target specific analysis needs.

## Data Storage

Results from both data ingestion and analysis are stored in SQLite databases under the `storage/` directory. This allows you to query previous runs or re-run analyses without re-ingesting the data.

## Sample Analysis

```sh
$ python . analyze ./prompts/large_caps.txt
```

```
## Overview of Candidate Projects

Based on the provided data the following projects are notable:

1. **VIRTUAL**
   • Market Cap: ~$812M
   • Mindshare: 5.41 (+44% delta)
   • Twitter: @virtuals_io
   • Strong cap size with upward mind share momentum and solid social engagement.

2. **Fartcoin**
   • Market Cap: ~$504M
   • Mindshare: 9.71 (–26% delta)
   • Twitter: @FartCoinOfSOL
   • Highest absolute mind share and robust trading/engagement numbers, though recent metrics are in decline.

3. **aixbt**
   • Market Cap: ~$225M
   • Mindshare: 6.59 (–38% delta)
   • Twitter: @aixbt_agent
   • Impressive social following (over 470K followers) and high community activity, albeit with declining momentum.

4. **ai16z**
   • Market Cap: ~$375M
   • Mindshare: 3.80 (+31% delta)
   • Twitter: @ai16zdao (primary handle)
   • Moderate cap with positive growth in mind share and engagement, suggesting emerging stability.

5. **ARC**
   • Market Cap: ~$183M
   • Mindshare: 2.40 (+28% delta)
   • Twitter: @arcdotfun
   • While on the lower end of “large cap” in this group, ARC shows positive engagement momentum and stable growth signals.

## In-Depth Analysis

### 1. VIRTUAL

- **Name:** VIRTUAL
- **Twitter:** [@virtuals_io](https://x.com/virtuals_io)
- **Market Cap:** ~$812 million

**Why It’s Interesting:**
VIRTUAL has the highest market cap among the group and shows a strong increase in mind share (+44%). Its substantial liquidity and relatively high follower count (close to 200K) indicate broad investor awareness. This combination of size and growth—despite a slight drop in market cap percentage—suggests the project is financially significant and generating renewed community interest.

**Comparison:**
Compared to others, VIRTUAL’s positive mind share momentum differentiates it from projects like Fartcoin or aixbt that have high absolute numbers but negative recent deltas.

**Confidence Level:** Medium
**Additional Information Needed:**
Longer time-series data, qualitative information about recent developments or roadmap milestones, and broader market sentiment analyses to confirm whether the positive mind share delta is sustainable.

### 2. Fartcoin

- **Name:** Fartcoin
- **Twitter:** [@FartCoinOfSOL](https://x.com/FartCoinOfSOL)
- **Market Cap:** ~$504 million

**Why It’s Interesting:**
Fartcoin boasts the highest absolute mind share (9.71) and solid engagement numbers (high average impressions and engagement counts). These figures highlight significant brand awareness and community involvement. However, note the declines in mind share (–26%), market cap (–33%), and price (–32.85%), which may signal short-term corrections or challenges.

**Comparison:**
While Fartcoin leads in absolute mind share compared to all peers, its negative momentum suggests that—even with high visibility—investor enthusiasm might be waning relative to projects like VIRTUAL or ai16z that post positive growth figures.

**Confidence Level:** Medium
**Additional Information Needed:**
More granular historical performance data, context on the cause of recent declines, and insights into upcoming catalysts or strategic changes that might reverse the negative momentum.

### 3. aixbt

- **Name:** aixbt
- **Twitter:** [@aixbt_agent](https://x.com/aixbt_agent)
- **Market Cap:** ~$225 million

**Why It’s Interesting:**
aixbt stands out for its enormous social following (~471K Twitter followers) and robust community engagement. Such active social dynamics often attract investor attention. However, the project is currently experiencing declines in mind share (–38%), average impressions, and engagements. This indicates that while the social base is large, recent community sentiment trends have been less favorable.

**Comparison:**
Compared to Fartcoin’s high absolute mind share, aixbt’s strength lies predominantly in its massive follower base. Yet, both suffer negative momentum metrics.

**Confidence Level:** Medium–Low
**Additional Information Needed:**
Data on the causes behind the sharp decrease in engagement metrics, potential upcoming strategic initiatives, and broader market commentary to determine if the high follower count can translate into renewed interest.

### 4. ai16z

- **Name:** ai16z
- **Twitter:** [@ai16zdao](https://x.com/ai16zdao)
- **Market Cap:** ~$375 million

**Why It’s Interesting:**
ai16z demonstrates a positive mind share delta (+31%), indicating growing investor awareness. Although its absolute mind share (3.80) is lower than some of its peers, this upward trend—combined with a solid market cap—can signal a maturing project that is gaining traction.

**Comparison:**
Its momentum sets it apart from both Fartcoin and aixbt, which are battling declines. ai16z’s steady increase may appeal to investors seeking projects that are on a growth trajectory rather than those experiencing volatile swings.

**Confidence Level:** Medium
**Additional Information Needed:**
Further details on community and product developments, additional historical engagement trends, and insights into competitive positioning within its niche for a more rounded assessment.

### 5. ARC

- **Name:** ARC
- **Twitter:** [@arcdotfun](https://x.com/arcdotfun)
- **Market Cap:** ~$183 million

**Why It’s Interesting:**
Though ARC has the smallest market cap of the group, its positive mind share change (+28%) and steady social engagement figures indicate growing interest among its community. The project maintains decent liquidity and volume, suggesting it’s active in market participation.

**Comparison:**
ARC’s combination of upward momentum and moderate engagement makes it a candidate for investors who are looking for projects in the earlier stages of growth relative to the giants (like VIRTUAL or Fartcoin) but with encouraging trends.

**Confidence Level:** Medium–Low
**Additional Information Needed:**
Additional context on the project’s roadmap, competitive analysis, baseline fundamentals, and longer-term trend data would be valuable to determine if its growth is sustainable.

## Summary

The analysis highlights VIRTUAL, Fartcoin, aixbt, ai16z, and ARC as the five top candidates among large-cap projects—with VIRTUAL and ai16z posting strong positive momentum, and Fartcoin and aixbt commanding high absolute engagement (albeit with recent declines). ARC also appears promising given its upward growth trend despite a smaller market cap in the “large” category.

For a higher confidence assessment, further contextual information—such as longer duration performance trends, qualitative insights on project developments, roadmap achievements, and broader market sentiment—is needed.
```

## License

This project is released under the [MIT License](LICENSE).

---

Enjoy exploring the world of web3 AI agents with data-driven insights from Cookie.Fun and Twitter! Happy hacking!

*This tool was created during the February 2025 cookie.fun hackathon.*

