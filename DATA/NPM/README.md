Create feature of groups management for hearted packages => create / edit /remove / assign to package / filter by group / allow Ai chat interface to assign packages to groups. This should be saved in xml when exporting, and properly upserted when adding xml file back to ui. To be able to save only hearted packages.
Enhance enriching process -> to save project's tree structure by using repomix internally to generate tree structure + symbol tree + initialization variables used in the project -> all this to be saved xml and upserted xml when adding it back.
Furthermore, to have one additional enrichment context -> Tags (User should be able to modify these, or ask ai chat interface to generate these after ai analyzes full project contexts. [short definitive phrases corresponding to project's features/ functionalities] - examples => Embeddings / RAG Vectors / Static-analysis / Dev-Ops / Researching / Routing / CC Skills (claude code) / Cli-Coding Assistant / Testing / Database / Visualization / API / Browser /
Also -> To allow saving collaborators -> To be able to view saved collaborators , remove them , view their packages with all enriched metadata.
Furthermore -> Hearted packages to be shrinked by package scopes ->
@memberjunction/ai-xai
@memberjunction/ai-openrouter
@memberjunction/testing-engine
Example if such 3 packages are hearted -> it should show
@memberjunction - [3] - Pressing on @memberjunction should list ALL memberjunction packages indicating saved ones and allowing saving/removing from saved while pressing on [<NumberOfScopePackagesSavedToHearted>] would list only saved packge scope's packages.