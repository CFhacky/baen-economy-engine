# Live Empire Source Census — 17 September 2026

## Verified acquisition

**372 live source rows materialized and hashed.** 5 collections fully enumerated against independent live UUID manifests. No simulation ran.

| Collection | Captured | Membership complete |
|---|---:|---|
| business_registry | 90 | Yes |
| locations | 182 | Yes |
| consequence_ledger_a | 11 | Yes |
| consequence_ledger_b | 10 | Yes |
| factions | 79 | Yes |

Whole identified core: 1381 rows; 372 materialized; 1009 not yet materialized. 5 of 10 collections complete. 7 retained contextual records are additional, not newly fetched core records.

## Coverage — CLOSED

| State | Materialized core | All stored records (including prior context) |
|---|---:|---:|
| SIMULATED | 0 | 0 |
| CONTEXT_ONLY | 0 | 0 |
| FUTURE | 0 | 1 |
| HISTORICAL | 0 | 1 |
| SUPERSEDED | 2 | 3 |
| CONFLICT | 2 | 4 |
| MISSING_MECHANICS | 0 | 1 |
| MISSING_DATA | 0 | 1 |
| UNKNOWN | 368 | 368 |

No core row is certified SIMULATED merely because it was acquired. Existing engine mechanics remain unchanged.

## Diff against preceding durable snapshot

Added records: 79; changed: 0; removed: 0; unchanged: 300; collection changes: 1.
Added means newly materialized evidence, not newly created in Notion and not a campaign event.

## Consequence Ledgers

All 21 rows retained. Seven reviewed links: one explicit supersession, three compatible candidate overlaps, three unresolved pairings. Four A-only and three B-only records remain visible. No canonical deduplication.
The charter A-row is a bookkeeping duplicate; B remains pending. Gauntlgrym has Overdue/45 versus Upcoming/0. Zariel's 200,000-unit scope and the standing civic/dated ceremony distinction remain unresolved.

## Evidence boundaries and next batch

Live Notion connector receipts are the source. This report is reproducibly generated from those receipts; regeneration does not claim another live query.
Selected database properties, including narrative Notes/Garrison fields and formal relations, are retained verbatim. SQL mention/formatting loss is disclosed; full page-body enrichment and the archived partition are not claimed complete.
Default UNKNOWN coverage is MODEL-PROPOSED fail-closed handling. Facts are SOURCE-DERIVED; only explicit source supersession is resolved here. Financial totals are not promoted to current liquidity or profit.
Next queued acquisition classes, in order: npcs, artifacts, threats, plot_threads, public_perception. Then page-body evidence and source-to-simulator coverage mapping, without advancing time.

## Every materialized core record

| Source ID | Class | Title | Coverage | SHA-256 |
|---|---|---|---|---|
| notion:page:2fbe8214-84b0-816a-b0b8-e7e7ed41fe29 | business_registry | Northern Crown Financial | UNKNOWN | `8c5da49d37baa3853b7153d476fc45278c7e8d80f567ffffc48e177f9d91e941` |
| notion:page:321e8214-84b0-8101-87d5-cfa2a74f31f0 | business_registry | Arterial Township Development | UNKNOWN | `fdf8792bd30343cdc5fe3f33f8a37cc5e1213ed96618778db3385a7dd86ddcb7` |
| notion:page:321e8214-84b0-8101-9287-cb7fdf65e5a9 | business_registry | Western Limestone Quarries | UNKNOWN | `e43ed5d4c587cd4a5158f2ea3fd7d21688951515ea17ee6612db8ecbd801f715` |
| notion:page:321e8214-84b0-8104-815a-fe1101e6f8f1 | business_registry | Thorn & Silver Exchange | UNKNOWN | `5d12c92f1823eec37d3fb8e6d17554b37461a2424b72f18b16ec741ac9ed0fd6` |
| notion:page:321e8214-84b0-8109-a55a-f30bd40fa6cb | business_registry | Northern Crown Financial - Suzail | UNKNOWN | `81fa3b025834d34c7b889dc5a58d422f19ab888edfabec866c66dd8a03153191` |
| notion:page:321e8214-84b0-810c-945f-f2ee5b1d4841 | business_registry | Underground Renovation Services | UNKNOWN | `24ed882980404cc010884e4a98c6fd0e524bc10eb1750d37bfb68bd62ddc3f3e` |
| notion:page:321e8214-84b0-8110-98cf-ebc200f16c7a | business_registry | Converted Quarry Aquaculture (5 sites) | UNKNOWN | `c8ca1d380241d6ea4ee7fdb157c0e27864b7a874c5d6d7ffe5c210533b77b62b` |
| notion:page:321e8214-84b0-8111-8df6-fb5d6377ba0a | business_registry | Treasury Stone Quarries | UNKNOWN | `b167f330be743e89a0859b10256ba2dd37a4b9fe29a6f2261404e369b2c4202f` |
| notion:page:321e8214-84b0-8112-ab9e-cd6f5eba18e8 | business_registry | Blacklake Aquaculture (7 pools) | UNKNOWN | `1bee2f20c7839b9f46bc5e2976268e16c2110a0f8ea003f0d39f3cc4e6a66655` |
| notion:page:321e8214-84b0-8116-a104-c6217060c1c5 | business_registry | BG Aquaculture Pools (3 sites) | UNKNOWN | `ef9f7c224d21c0ec4c6a37a7fc6452746952e9488e69d26f0f29baa6c112ce88` |
| notion:page:321e8214-84b0-8116-ac1b-cc07c68ff15f | business_registry | Gauntlgrym Tools Partnership | UNKNOWN | `a59cdde145f60f8eed402eddc0796ee8f98b20fffacc5cc8546ad23f0ab024e1` |
| notion:page:321e8214-84b0-8119-b068-e3d4d503eaa3 | business_registry | [SUPERSEDED] Guardian's Gate Settlement (older variant) | SUPERSEDED | `daf98ac95eaec83f71c4b63cb2b2c0e334b9c99828ba0f50a5c89d0207c0fe35` |
| notion:page:321e8214-84b0-8120-8756-cd5f9b876869 | business_registry | Commercial Properties (Various) | UNKNOWN | `a92684d75c82b18aa450e852ded70ca9fc00801724d5a9b01891e5ec83d1fefb` |
| notion:page:321e8214-84b0-8122-9dce-efa0c3c48170 | business_registry | Baen Construction HQ | UNKNOWN | `433f0d7a487ee1aa8dd0aa02a038c1e9f2b754b1fe5d6f3bc40db9a945038073` |
| notion:page:321e8214-84b0-8128-9cb9-fbb308ea2536 | business_registry | Waterdeep Trading Office | UNKNOWN | `f82d1b812da641ed656926458a492bc284b01c53fbb7a8bcc34e8983a3d2f79e` |
| notion:page:321e8214-84b0-812d-82f9-cc0add910698 | business_registry | Northern Crown Financial - Luskan | UNKNOWN | `26147bf70027aaf433bb012d21e1b5125858850c58f503d61b3087128e860b34` |
| notion:page:321e8214-84b0-812d-bba0-e10b75086a02 | business_registry | Bloodaxe Legion | UNKNOWN | `26af6f585cf28a8af85b0fe318a78af14c66801e7acfd18a726324300d45bc19` |
| notion:page:321e8214-84b0-8132-bcc9-ef2290e366bc | business_registry | Dock Ward Warehouse | UNKNOWN | `d79a136e1ccb5216159986baae4aa6378157e54bc50349fe9650281787951cb5` |
| notion:page:321e8214-84b0-8140-8f8c-e78bbfd11b30 | business_registry | Diplomatic Operations | UNKNOWN | `59102d350f5eff77cdfab5622d4d1dc486e12995e1ca30e60d09346b4afe4b6c` |
| notion:page:321e8214-84b0-8144-9c69-fcb641741a06 | business_registry | Green Vein Corridor | UNKNOWN | `c13ef31c30edd46f27382c486801974bfb5965f7ce2d91d7e7134b1d3e0f0516` |
| notion:page:321e8214-84b0-814a-9a3c-ea9157b13d6b | business_registry | Venetian Bay Housing | UNKNOWN | `8991ede7fdcae84c52711cbf3cfbfb27c55f9c69775fb943fcee56b75b98be19` |
| notion:page:321e8214-84b0-814a-9cd7-daca52d0c750 | business_registry | Specialized Vault Construction | UNKNOWN | `ddbb37bcda7c89024826e7598be7003d27d1c08eef765fb1f56822c9fcefc563` |
| notion:page:321e8214-84b0-814c-9919-d340642e3319 | business_registry | Canal Housing Redevelopment | UNKNOWN | `42c9a116eb74fdde084a5631e063db6809f8b957adfacb390f56fa28d721fa3f` |
| notion:page:321e8214-84b0-8151-be78-c309a7ce8475 | business_registry | Enhanced Shoreline Systems | UNKNOWN | `908e6e099e47f6e9e943882404ef753da271b0e96c560fbafddd4ed5c4d67a57` |
| notion:page:321e8214-84b0-8155-bf9b-cea55e2c7669 | business_registry | Silversheen Trading (Aluminum) | UNKNOWN | `38fb2ef52868d662ec46ddf2f96273d4ce114fec0cf08f39bb4231120faeb888` |
| notion:page:321e8214-84b0-815e-97ff-e0bcec9a3ebc | business_registry | Celestial Springs Bathhouse | UNKNOWN | `d986e539d58d86433b321bbc2fc154eecb0dfb85ac914de3c7bc04e792f2fb71` |
| notion:page:321e8214-84b0-8169-bde3-cc7112ca328d | business_registry | Northern Crown Financial - Waterdeep | UNKNOWN | `b54d95a6496958d2996909dae4ecf37ce0ed894de6669d55bd241ccfc79f59f4` |
| notion:page:321e8214-84b0-816a-8684-d3df85527df8 | business_registry | Warborn Production - Waterdeep | UNKNOWN | `f892b0367691f7030b8589813cb4fac4ceaff8d6526046f224bfcd0b36893669` |
| notion:page:321e8214-84b0-816b-ab1a-c84039fbe89f | business_registry | Crownsite Canal Property | UNKNOWN | `f09f98578d6e0cc3e068626562974bd3bd97597b3de9d729d7dda52dd347c122` |
| notion:page:321e8214-84b0-816c-87fb-f0fee22835ad | business_registry | Baen Brickworks | UNKNOWN | `2496a684a1699a0088d89c254265ca2ea35b473cd22aabefe29707ebd496c37c` |
| notion:page:321e8214-84b0-816d-8ca6-d53a98b8ba6d | business_registry | Maritime Operations (Planned) | UNKNOWN | `34b271c6098d20cee78bfd2981590442ea0b2f0c5be38fae75e6d77f8b2b4dad` |
| notion:page:321e8214-84b0-8172-9b7c-db66323883e8 | business_registry | The Veil | UNKNOWN | `efef03337d49e4b4708ee2c2d5779f92b477f1077a9cdaa71d5a3fa5bc758c25` |
| notion:page:321e8214-84b0-8175-997c-c81e61c35015 | business_registry | Northern Crown Financial - Neverwinter | UNKNOWN | `4b10e30dbf0d1ff140829834db3593993b8a0b7327d4f5b08842f8902d79c99a` |
| notion:page:321e8214-84b0-817d-a905-f79b60a61485 | business_registry | Split Fountain Renovation | UNKNOWN | `3eec24f62e5ed7992f01c13531be107ffe2ef06b7c61a40b88e9aac861a48c53` |
| notion:page:321e8214-84b0-8189-9107-d6fd75176754 | business_registry | Lobster King Operations (Baen-Allied) | UNKNOWN | `e339d9ab86eccb191e6bde867438c736d9b7b04f911f812dccb961d599dc6ca6` |
| notion:page:321e8214-84b0-8192-b481-f813840aadd3 | business_registry | Western Sandstone Quarries | UNKNOWN | `632174cc3468af0bbdf88724ce773360ef06b9645e33554a202e127e0564b96a` |
| notion:page:321e8214-84b0-819e-840a-ea69126c3105 | business_registry | Northern Hammer Smithy | UNKNOWN | `d6209dc8351e4217aeb92f6ac7fa6e37a6a816104ef27c564f5a211b3ce1e4e0` |
| notion:page:321e8214-84b0-81a0-9fde-f55820cab72b | business_registry | Waterdeep Information Brokerage | UNKNOWN | `89f8555c56b78ae209ac229c795a885bf4270d2a07d187506e657627899b4b2d` |
| notion:page:321e8214-84b0-81a8-b47d-c47579a6e346 | business_registry | Castle Operations | UNKNOWN | `2f951bde30997b001deee99c8f00b382120ba81d3c7893e989c0ef16ef0de257` |
| notion:page:321e8214-84b0-81b0-9469-f6c9d92a22d5 | business_registry | Forgedeep City Development | UNKNOWN | `163fdaca80d0e55ae7030e480d5e3ac419fb7ff8d5ab7db6a3439c5613ef5a2f` |
| notion:page:321e8214-84b0-81b2-8e6d-c97122a34793 | business_registry | Azurite Decorative Quarries | UNKNOWN | `388855cdf2edd2078f0216f6ce71bd4d075d0562c8d796c23cfba4b2218c0b5c` |
| notion:page:321e8214-84b0-81b3-8d51-dcbc19edd667 | business_registry | Warborn Production - Neverwinter | UNKNOWN | `a8ebc7ad060cef2c4f479de7f9f94f45793fa9dc899f60c2a80b77bfff85c0a2` |
| notion:page:321e8214-84b0-81b8-8ac4-d7cb4a1b4b0c | business_registry | Safe Harbor Inn | UNKNOWN | `a1389c8a7f1b09b8ab4b8142a9d81965e382310d827bffc86adf07543d7b4d19` |
| notion:page:321e8214-84b0-81b9-a4cb-f9fd26c7eccf | business_registry | Hunding Canal Lock System | UNKNOWN | `58700be64a94793f369941e59a854f08ff77713723b3151cdbba7cd4ca968d6a` |
| notion:page:321e8214-84b0-81b9-b209-d6dd21f950f8 | business_registry | Dock Ward Security Corp | UNKNOWN | `316988210426fa5ef9162f41adf5987976fe2d8ef21d248dece3226caee4746b` |
| notion:page:321e8214-84b0-81c6-9bde-c30dd49bc5b6 | business_registry | Neverwinter Clay Quarries | UNKNOWN | `4fbcb85749c075d926281ff5ee023c545909442176e5ed8129f914ae8fb4b060` |
| notion:page:321e8214-84b0-81cb-b112-e8cab733e992 | business_registry | Star Metal Hills Bauxite Mining | UNKNOWN | `1f9dea189026b55b0646ab5e46ca6cf195d0368646e8ec142e05fec5de3fc33a` |
| notion:page:321e8214-84b0-81ce-b8ce-fafb60bf5d8c | business_registry | Arterial Road Network | UNKNOWN | `e0912e0ffb0d2e92a83c038e59c0f3ef9b6cd719dc3f45bdb159ed2265ec2e7d` |
| notion:page:321e8214-84b0-81cf-b8ef-c87bd6feaaf7 | business_registry | The Cerulean | UNKNOWN | `e5a5c3288d9e0345e3ed84948df007852f2dc5b4b827239a6738f7bd4d92c2cc` |
| notion:page:321e8214-84b0-81d4-921f-ffe136c22209 | business_registry | Verdant Cascades Bathhouse | UNKNOWN | `9754537214d77b28cb9eb605d5a92063cb11928710a1e62aeffb6c061680005c` |
| notion:page:321e8214-84b0-81d9-9801-d601f9503056 | business_registry | Northern Crown Timber Operations | UNKNOWN | `7afe563a15e1c526485313e6aaefe22037feb6868e262434a1b0c2351fb4571a` |
| notion:page:321e8214-84b0-81dc-ae68-d45f3e3801db | business_registry | Dock District Mixed-Use | UNKNOWN | `6e37570eb6e7cf71f37cc973bd5c493f3f3c468bdbbeb4c24ffa5a37262a7eb0` |
| notion:page:321e8214-84b0-81e0-9660-eacd14973b2f | business_registry | Agricultural Shelter Zones | UNKNOWN | `b5a144666bdcab51428522ee8a89222b446d411544bc2efd4b9c8b652a5f925b` |
| notion:page:321e8214-84b0-81e7-a5ec-fd25ff8299dc | business_registry | Gold Lending House | UNKNOWN | `7024e80e17c49c8bb8cb68a15a5ac28c0092998b0b2d9cc09453e42abde3fda9` |
| notion:page:321e8214-84b0-81f6-a74c-d6ee2b88a08e | business_registry | Reservoir Fisheries | UNKNOWN | `c8936926df32109123c6582dd98fada3b2a992eec3f02869b82d1dde8a8069e4` |
| notion:page:321e8214-84b0-81f7-be17-ff26a67e57fb | business_registry | Verification Services | UNKNOWN | `a71bb7da38131c58b8aead5ba94101d3634ceed5432b6b74fb16b837c560eea4` |
| notion:page:321e8214-84b0-81f8-8632-c9a3a854424c | business_registry | The Lustrous Blade | UNKNOWN | `9c95ba4e7b64226c03f24b463fa474f648652e70f4a479cee579a6fda7e7ec88` |
| notion:page:321e8214-84b0-81fa-ba57-e5f9a87ab3a9 | business_registry | Dock District Housing (Ph 1 & 2) | UNKNOWN | `ecc22d3d9067fc56f97ccfd042fd10b277a916930c22e4425b9022ebe4cbcfaf` |
| notion:page:324e8214-84b0-813f-b1c6-ecc41384257b | business_registry | Neverwinter Athenaeum | UNKNOWN | `8ef85ab057b97ceef778e6d3268f970e81d003f8cf8be1c9442cd6457052fe4d` |
| notion:page:324e8214-84b0-8169-9a22-c992b7e05649 | business_registry | Devil Academy (Philosophical Faculty) | UNKNOWN | `60786f9a64a70cb8ac846542028d56e0dd4a056d08c381780f866dc095d867f0` |
| notion:page:324e8214-84b0-8175-ae3c-c451aea28565 | business_registry | Collegium Montis Gladii | UNKNOWN | `bad2076cb84f44284d17ac9ad628f49464b067f06b257ddd73aaa65712781b76` |
| notion:page:324e8214-84b0-81f3-b801-f03fc8ec343d | business_registry | Schola Ducum Integrata | UNKNOWN | `91182386a1a23ae3f34ea54a588267d80d8b00bf5c868e5f20402f09608bf942` |
| notion:page:34ce8214-84b0-8111-9fd4-c41feef5634e | business_registry | Shimmerdeep Cradle | UNKNOWN | `bc8b5853651324983c2d841766ad6db0fa012374639ca2ab8664c33befc4e0dc` |
| notion:page:34ce8214-84b0-8125-b0cc-fa8966ff42f0 | business_registry | Project Burning Gate | UNKNOWN | `23e5bc3469c4d57258252dd98b0def6744d62ed5e8378b4c2467933d3e83b8ed` |
| notion:page:34ce8214-84b0-812f-8577-d4d37289da9f | business_registry | Wyrmhelm Forgedeep Facility | UNKNOWN | `7bfe114daa41723b213f930de3895898b0705b3e458044ee668c51519bb5cc49` |
| notion:page:34ce8214-84b0-812f-97cc-e7bf7af67928 | business_registry | Crown of Eight Springs | UNKNOWN | `6cc155c377e56bbd310feda4e3483b2846a7cb79ab1ac0b0392bb236a78ab815` |
| notion:page:34ce8214-84b0-8130-aedb-f6d099d79bfb | business_registry | Orchard Chapel | UNKNOWN | `a9e6e8335637424a5f07603f54f8aca1a8579a748bf43c0f3ebd83fb37f9a5a5` |
| notion:page:34ce8214-84b0-8158-a449-c58b59fbc2fd | business_registry | Crystal Gardens | UNKNOWN | `3a53244dd43517f6751494e9caead03a193b274ae89c367eb1600894e63c0be8` |
| notion:page:34ce8214-84b0-815b-8025-e995ced7c996 | business_registry | Neverwinter Municipal Water Corporation | UNKNOWN | `2e1a0a5d476e1afb5d9f551f576c9a3399df8e8175e257d33afebe0acaede6c4` |
| notion:page:34ce8214-84b0-8164-aa0f-d2d0083834c8 | business_registry | Threadbaum Model 1494-L "Whisper" | UNKNOWN | `a0d1ef8a932237994767c872d2559946532247bcb770e59f196efdb1437a276c` |
| notion:page:34ce8214-84b0-8172-b32e-f083715f9465 | business_registry | Desertsmouth Tunnel — Trans-Mountain Canal Passage | UNKNOWN | `ab7c17cb1f9161dbdf6445a2547f9b6f40b014642467f54f54a07475904d4ad8` |
| notion:page:34ce8214-84b0-81a9-8fa4-c44ac30bf8ac | business_registry | Crownsite Canal Property BG | UNKNOWN | `840608c20a6aacd21915d328c0d2b7f5913947af8e3a041a1f00d5bc6b2fac56` |
| notion:page:34ce8214-84b0-81b9-95b9-f3426792b6bc | business_registry | Formicorps | UNKNOWN | `1cafbe7ca0cf384b2ce0da4a4a3709617d1aa23298251ae716097cc75e2b1c9f` |
| notion:page:34ce8214-84b0-81c2-beea-e2858f85995d | business_registry | Dawnwood Settlement | UNKNOWN | `1b601b62ce475bca0cbfb56a4e49747bfdfd37e0bd115c98777b3fa7870ccf90` |
| notion:page:34ce8214-84b0-81d7-aaf3-fb4e6a607477 | business_registry | Skyreach Castle | UNKNOWN | `0fa2d4d71c68c60af04ee442076d7fca3f316ef5587048efb9a1e608bd71b130` |
| notion:page:34ce8214-84b0-81ef-b974-fa3f64c20be8 | business_registry | Arterial Road Crystal Network | UNKNOWN | `f57dae35fe34de9d7b47f2bd0c6bf0859ec08cda907944752861a11d33d98afa` |
| notion:page:34ce8214-84b0-81fe-bf14-f062ef3cb91b | business_registry | Zariel Warborn Contract | UNKNOWN | `28a4ea69c0ffe219f76e608dcac47a24a21db6799418ae88e58c4b387dcef7f5` |
| notion:page:362e8214-84b0-813b-9b7e-f67d1559fd89 | business_registry | Faske & Halloran | UNKNOWN | `2d1bae33bd61bb570230e8161ffd7238b1179a835c7d20243ec0e5d44a941406` |
| notion:page:362e8214-84b0-81e9-8ce5-d318425ffcde | business_registry | Neverwinter Munitions Facility | UNKNOWN | `9e4fae4b9f652f6cbf280927899c0d3c799b13193327961c847eba7cb984086c` |
| notion:page:372e8214-84b0-81d9-8c19-e650c16b687f | business_registry | Institut de Tissage Arcanique | UNKNOWN | `183ad3686f54f15a02789fe41a5103c9720cfe494423a55a68f03af8498d17ce` |
| notion:page:376e8214-84b0-8108-8810-e1d99b58f959 | business_registry | Thundertree Waystation | UNKNOWN | `aad9b9f87695391904c88e1d748855d7f7f8a382c26e7df0e151f82f54249ed3` |
| notion:page:376e8214-84b0-8121-88b4-ced3087746f7 | business_registry | Seven Spires Estate | UNKNOWN | `0c3932fd5a8900a5b0896c4ee90e1f25726111e05b6fd5840041c89116106de6` |
| notion:page:376e8214-84b0-819e-8c07-d304487c01bb | business_registry | Sea Gate Harbor Authority | UNKNOWN | `7485b7dddf42a10df13f86b92d77d328b199bca5afc06d198d9dd31652c60586` |
| notion:page:376e8214-84b0-81c1-95a1-d5c3e2ceb4cb | business_registry | Neverwinter Wood Canal | UNKNOWN | `e13a7be770fee385ef00e3dc33acc3b5b4d3b4637729e3522167d954b4f6c909` |
| notion:page:376e8214-84b0-81db-9a8a-e682a583b6ee | business_registry | Sea Gate Shipyard | UNKNOWN | `f01789bbe7ec696af474e40690d2b447c9ac0884f88aab616841c992585129b6` |
| notion:page:37de8214-84b0-8154-9c6b-d10986768d97 | business_registry | Baen Real Estate & Housing Portfolio | UNKNOWN | `d2267961af3ba61e1d9e8d00ffe5fcda27590647e067ba6311354a0e399a8f70` |
| notion:page:37de8214-84b0-81d1-bf05-cd5b4111d5bc | business_registry | Stonefire Ceramics | UNKNOWN | `e0f1f40bf2d833974afea69c5387bf7deb39c364b16398275ed3a78ebc6bb3db` |
| notion:page:392e8214-84b0-81ef-b0a9-d73f9b9757d7 | business_registry | Scales & Secrets Asset Management Trust (SSAMT) | UNKNOWN | `a71bdd72d271696484ab6e7cf73073c8ad6bfb8fc68c927a4426c8dcaf85678f` |
| notion:page:3bbe8214-84b0-815f-ac80-dd1c4430327d | business_registry | Deep Road Network (Deep Road Authority) | UNKNOWN | `d9290cae3d2bfc37d94c2d41ae2c3d89f93fc54fd8259a17d1056af78779cf4e` |
| notion:page:3c2e8214-84b0-81f8-88a6-e1169f9a4df4 | business_registry | Snowfall Hearthworks | UNKNOWN | `515cbc6215e9d9a53f5ac07ed9711379ae7531c9160fb29a1fa27344b6d63bfb` |
| notion:page:323e8214-84b0-8134-a432-f9a1e4d3f8b3 | consequence_ledger_a | Discuss eastern deployment resource allocation with Korgan | UNKNOWN | `ac8b862765a33665209067f8b112c6cf0f1f41fcd7daa48bb8760f148298df15` |
| notion:page:323e8214-84b0-8146-a6ed-c334fb99592d | consequence_ledger_a | Prepare Forgedeep charter review before oversight committee visit | SUPERSEDED | `f47a454318e391010f23e385eb30f2aca1a125d3caa9b0bbd5556a26b337982b` |
| notion:page:323e8214-84b0-818b-848f-c2463bd5270a | consequence_ledger_a | Talk about baby names this weekend | UNKNOWN | `5ddc1f4f5b87db28460ecbb780747842a23a2f180da72a240c8474705102239e` |
| notion:page:323e8214-84b0-8190-808c-c962243ce5af | consequence_ledger_a | Inspect unidentified crystals at Star Metal Hills eastern gallery | UNKNOWN | `c7e2d15aa51bb96b77e1e4358ba77e0d4ffe7e366e2672c9685249fb57c24641` |
| notion:page:323e8214-84b0-8199-9808-c4cb7a0fb555 | consequence_ledger_a | Zariel contract: production milestones per agreed schedule | UNKNOWN | `2e46055185f7d2d3fc83e78e7703c6971aefb7b325b4f924b629a98d92c8f31e` |
| notion:page:323e8214-84b0-81a5-ab8c-e281286128a1 | consequence_ledger_a | Investigate timber market before Dassyr consolidates supply chains | UNKNOWN | `609dfe440658b34259ecd19fe73d36f9bbdcc8a38453888f50390d83365a6deb` |
| notion:page:323e8214-84b0-81b5-9e37-ea05de7941b4 | consequence_ledger_a | Attend Coronal Remembrance — elven ceremony for fallen Cormanthor leaders | UNKNOWN | `74ebe6aa6616f199ca2f99897885dc510c440f5de8a3aded36c5c3de08258cd6` |
| notion:page:323e8214-84b0-81d6-9a15-e4ad05af6f0c | consequence_ledger_a | Attend Harvest Remembrance ceremony as notable citizen | UNKNOWN | `3be7242a2f48cfacebf2c135d33f37780526b5a51295a0b14439b80172e18f22` |
| notion:page:323e8214-84b0-81db-885e-d9acb18225b8 | consequence_ledger_a | Check on Mila Dunwright's aquaculture operation — something felt off | UNKNOWN | `2aef9c44d6d70e328288d6f445fba72138aca9cfbb167dfc9b2758e7ad31c964` |
| notion:page:323e8214-84b0-81e4-b90b-ef7ddeed74c4 | consequence_ledger_a | Review Kalnar's experimental construction technique proposal | UNKNOWN | `893db8cfeeb2350b74f4776531215b73489bc3d7ba7e2ebb543234bbaa092df5` |
| notion:page:323e8214-84b0-81e7-a912-fe3389a5f75a | consequence_ledger_a | Provide engineering support for Gauntlgrym lower mine expansion | CONFLICT | `62ce9ea8b297facd4498c9f7fdf00a75419a8a4b38d07a781465ec617db4643b` |
| notion:page:323e8214-84b0-8118-a899-ee4de3c6e713 | consequence_ledger_b | Neverember civic cooperation: attend public ceremonies as notable citizen | UNKNOWN | `48aeecc9742863651e6c5d7b71196f7cbc7d145bd4cf59d7cba2f358ee84847f` |
| notion:page:323e8214-84b0-8122-ae2b-e1bebef4c027 | consequence_ledger_b | Zariel contract: 200,000 Warborn units on production schedule | UNKNOWN | `9421ac67d50bee91074600a2b6c8c2bc02304b15ff4a990a06627a2058a13a2a` |
| notion:page:323e8214-84b0-814a-b3cc-dcd7434d99ae | consequence_ledger_b | Check on Mila Dunwright — something off in aquaculture numbers | UNKNOWN | `20c0931fa07601093743faad91b766c1b8da941b4a74d50ccd59c6003405b89a` |
| notion:page:323e8214-84b0-8157-8f0f-d10c1910e8df | consequence_ledger_b | Investigate timber market before House Dassyr consolidates | UNKNOWN | `65c4b820c1d1ed9cd9a4c4b6fbf5fc8b31c0d21dfc53fce89d132e439bd332f9` |
| notion:page:323e8214-84b0-8187-ad22-da8ba4c1e10f | consequence_ledger_b | Formalize political succession plan (regency council) | UNKNOWN | `224e40eabbcce4b05f26eabaccb6a093b53ab2994da3b597289158bdc5bb57bf` |
| notion:page:323e8214-84b0-81a2-a79c-e468eb4c636b | consequence_ledger_b | Find Alassra Dawnstrider (Simbul) for Elminster | UNKNOWN | `1b020a4dec2c470f9aed852337c1bafd4b22cdd0fe6fe0f17ec62df07c605633` |
| notion:page:323e8214-84b0-81af-9a0c-cc0f8a23586d | consequence_ledger_b | Elara's court: attend Coronal Remembrance ceremony | UNKNOWN | `27fbff6ded1d816464b761c0b79b3a03f27905147e47adcf0b8262d0edb2a6ef` |
| notion:page:323e8214-84b0-81bd-8195-cc09b1652d1d | consequence_ledger_b | Formalize Forgedeep charter review preparation | UNKNOWN | `6d55f5fdacaed7325f764ea525331535974562c0299337945c832f5a74b8cc95` |
| notion:page:323e8214-84b0-81e7-8275-d1f27d8a270d | consequence_ledger_b | Establish formal apprenticeship / training program | UNKNOWN | `fbe5e205a12e5f65df78788c4643c788b2cda081e98ee2d91518bbcb7163594d` |
| notion:page:323e8214-84b0-81ed-8ab7-ed48df5c2d07 | consequence_ledger_b | Gauntlgrym partnership: engineering support for lower mine expansion | CONFLICT | `ff2a174b3d68876e74f1e055fc90963b84f0e5d9202b115b4812fd5b9efc1f8e` |
| notion:page:2fbe8214-84b0-8123-91b5-ec2e34d09ac5 | factions | Lords' Alliance | UNKNOWN | `de5f1f11b3db1deaa62f2bfb0e0ba43ccd173de180e724a0723380b1b2bbe4e5` |
| notion:page:2fbe8214-84b0-812e-884c-cc3815fe582f | factions | Iron Sovereignty | UNKNOWN | `4ac394dff205044a505b65f5e0dfb60afcb81e2cd7b593e7807f0c993566c301` |
| notion:page:2fbe8214-84b0-815f-ba19-e874f0becc19 | factions | The Veil | UNKNOWN | `dfe66de6e5268ab2679d1a482ad9a5214b43bf6217f2665f7fde3a619d3b63f2` |
| notion:page:2fbe8214-84b0-8161-a02a-fe4c68fc8f6d | factions | Bloodaxe Legion | UNKNOWN | `c3356a6d824d54655b261b5152592e3daedb24dda3520bf6beb1b91304471916` |
| notion:page:2fbe8214-84b0-8165-ab14-c8c669cc58b3 | factions | Gauntlgrym Dwarves | UNKNOWN | `b6c0761adcd7267dbd897e83afbed725860c8a3a6cd67f968333a13b67b790e8` |
| notion:page:2fbe8214-84b0-8167-b265-eac0d0df5a93 | factions | Bregan D'aerthe | UNKNOWN | `b10f7a75c2a8c520214960637979a9c3931bc6f6ab20f419d0240a47c0e53a1c` |
| notion:page:2fbe8214-84b0-81d8-ae87-e3bd80ce0a54 | factions | House Baen'und (Menzoberranzan) | UNKNOWN | `3904002e1be1c6a1315cb8e96e9ed5a7318559054d1934c6628fe94aaa387e15` |
| notion:page:2fbe8214-84b0-81d9-a18b-f06988cea7b9 | factions | Moon Elf Alliance | UNKNOWN | `be83b62732b486d95daeeb5e7a3668ae297d19b2dd3d002918f5e9a182360ad5` |
| notion:page:2fbe8214-84b0-81d9-bc8b-d10ad1ba785a | factions | Institut Baen'und | UNKNOWN | `48ead747aa4092d3abfd90df33a31a002ec493fe0ddbe64b38541b6924d89367` |
| notion:page:2fbe8214-84b0-81ef-80a5-d67f7b7e6f31 | factions | Baen Enterprises | UNKNOWN | `b6813156cb662c677fe299a0cc6607211c1974f187d6a8a2663b0659cc199f2f` |
| notion:page:2fbe8214-84b0-81fd-bdab-e411d421d64e | factions | [TRASH — H4] DELETED - DO NOT USE (tombstone, recycle) | UNKNOWN | `529365906c902908933a1d1276bc2a1524f899a63b3d4d7435bb3acd6a23ab67` |
| notion:page:32ae8214-84b0-81d5-9df3-eac77416c849 | factions | Sembian Council of Merchants | UNKNOWN | `3842f59a514a5aa9f2a3e94399f2225f20a4e3b0921d7bcfe334a20b22147af7` |
| notion:page:32be8214-84b0-81c2-a5a0-ee17bed6b8e7 | factions | Bloodaxe Legion Mage Cadre | UNKNOWN | `a7c391a9fc4216fcd8c2339d37343613b7b01ddabb4a19e826b801430fac6ca3` |
| notion:page:32be8214-84b0-81e4-84bc-e5ac1ab8e015 | factions | Eternal Dancers Program | UNKNOWN | `d5deed92b13033dd890af87e20b44a8e7d1683308e90b99d2895703138c6b7f6` |
| notion:page:32ce8214-84b0-81c4-87f6-da40d3ab1a7e | factions | Bloodaxe Diplomatic Escort Element — Operation Cardinal Support | UNKNOWN | `48fab8661b49f8d5a6d5df241520141414b831c06080b20fe0e0f1cda5d7fae4` |
| notion:page:338e8214-84b0-8146-b362-f1bfdcfc91a7 | factions | Thousand Silences (Al-Samt al-Alf) | UNKNOWN | `1d89402656c93360db864952ad7d13b4fe9353925feb4e2f4897c999cf8414f2` |
| notion:page:34ce8214-84b0-814d-853b-cfc46b2a0d36 | factions | Al-Rashid Clan | UNKNOWN | `e707628d64edf0d46988c4ac9656f11c591c25c1af80e9c728e9d2953adb8cd7` |
| notion:page:34ce8214-84b0-815b-beb3-e3673d49d14b | factions | Shade Remnant | UNKNOWN | `49a3a05c0bd9eed7e2c37078aa58173621f111d8697b93dd30d1c79c661dab06` |
| notion:page:34ce8214-84b0-8199-afdb-e5a9fa617158 | factions | House Amaranthe | UNKNOWN | `3ef027d4f6c7a98bbd2dbb07cf22f5d81c42771c6c7d6a0f3b833733acff99a5` |
| notion:page:34ce8214-84b0-819d-920a-fb6683f4e988 | factions | The Thayan Delegation — Red Wizards of Thay | UNKNOWN | `96042d668ec4f5dc4e30f7dacdfb72632311f71850d7436f861981449c805a34` |
| notion:page:34ce8214-84b0-81a4-bd09-f7f074b83cd2 | factions | The Argent Tide (Silver-Eyed Faction) | UNKNOWN | `4e4cc66d32df23b8670b894f21d90c45adbc10e1326409887cee7104bc5ec1bd` |
| notion:page:34ce8214-84b0-81a7-9506-ffca52327874 | factions | Purist Assassination Cell | UNKNOWN | `cf3f0ebc0a5ac532d8af9b2610aa1728f3fc2ea382e955e2af1583fff4d793ae` |
| notion:page:34ce8214-84b0-81ac-ab5e-ce56184c8614 | factions | Al-Saif Clan | UNKNOWN | `8f5b2421781a1f254520f6871f5b436e271b3c259e700927a2c03900d4bab10f` |
| notion:page:34ce8214-84b0-81ad-8efe-c4119b8d50b3 | factions | Angel Wing Griffon Corps | UNKNOWN | `060ffa05ae1629b635d3aa0dbf5d631719aa327372e431848dc915a528beb42e` |
| notion:page:34ce8214-84b0-81b0-a14b-c768b5efbcd7 | factions | Order of the Storm's Edge (Emperor's Talons) | UNKNOWN | `c55a432ea9fe5f8a2c0241d38172b37b1b217e738b95c60b17f8f5a4ada1e738` |
| notion:page:34ce8214-84b0-81d8-97ee-dbe2fb005457 | factions | The Zhentarim | UNKNOWN | `fa6f2d5f9f004a6d7c6af03bc6a4ba90bb61eb701e4f019a3d220e6ade12b2ce` |
| notion:page:34ce8214-84b0-81ed-8658-d74dbf3f7539 | factions | Cult of the Dragon — Eastern Cells | UNKNOWN | `73e790c216c029221af5c773243afe17e36f9c8095b9eac7607ee130791bc9da` |
| notion:page:34ce8214-84b0-81f1-b228-e214adb50c0b | factions | Bloodaxe Halfling Scout-Sniper Section | UNKNOWN | `99147b946ecb1d6837b068f2ddfbbb011545577b3debda72a8b0d8d8c5d33d45` |
| notion:page:34ce8214-84b0-81f2-8cd4-c990f5b90e97 | factions | Margaster Asmodean Cell | UNKNOWN | `e2ca2f7451c1b458b542300e5d81bfb21d82d9b41b345df03ee80e7c5d11db7c` |
| notion:page:368e8214-84b0-8117-9096-d8c6a32bd357 | factions | The Elturel Cohort | UNKNOWN | `c6cfcec9e694cdd3bc6d7c292bce54729673cab4ad35fe302927572beb384e18` |
| notion:page:36ae8214-84b0-8105-b235-e03f513232a8 | factions | The Sunbroken Lances | UNKNOWN | `20d954ecfda1562a1632c120ebe5c7113446195bcf23dcca6ce4e1c1d84fffb9` |
| notion:page:36ae8214-84b0-8113-8a6c-f90a3b8207f7 | factions | The Oak Father's Circle of the Delimbiyr | UNKNOWN | `3f2b06a5469c3f2a5563d64976c6ec220aab0b34f8bd960a9d5e47608404bda3` |
| notion:page:36ae8214-84b0-81f7-835d-e500affe72fe | factions | The Rimewardens | UNKNOWN | `dd6b8d09ef4028aa9c258d0039816999b2b52336ccfee7a5253e48b49232d027` |
| notion:page:371e8214-84b0-81bf-a7d3-c0f4a3a7901d | factions | The Magisterium Verbi | UNKNOWN | `46395a041c4d7c0ff15361fdc89c49a4ee42715e46530e6f6aa64b4212d4675c` |
| notion:page:375e8214-84b0-813e-970f-cadfa3c98e0f | factions | Order of the Warded Moon | UNKNOWN | `b63a76c4f96d867b8e6136b570b2ccd5574cce64a0e9a7587e12c9dae39d2269` |
| notion:page:377e8214-84b0-810e-a2b9-c27e1ac73efa | factions | Eldreth Veluuthra (Victorious Blade of the People) | UNKNOWN | `19eef07156ee2ba0bf12c44013a5f2c2831ae40b39d9755ebc77f6da64dc03c2` |
| notion:page:377e8214-84b0-8188-8267-d15607032249 | factions | The Court of True Cormanthor (Maerithra's rival exile court) | UNKNOWN | `0f0f976b139e20c320143991d58413ef4b3f173605e15e2c87a1445dd751b6f3` |
| notion:page:377e8214-84b0-81aa-9a34-cbb42e0f2cd4 | factions | Kurrimal | UNKNOWN | `d5d60b6100c1340c7cf400cddb1bb51245904e46bdfa2385697d8c4901bea149` |
| notion:page:377e8214-84b0-81f7-9b52-dd43846aa244 | factions | The Coronal Court (Contemporary) | UNKNOWN | `9cce83f7d1b0f6e292002648be173e2356ff0e31e0b2ea6e41507f5e36ab5819` |
| notion:page:378e8214-84b0-812a-9b0d-d6e3f23c8bfe | factions | The Bloodbone Clan | UNKNOWN | `96d62991607d5906ac7c255a4354624272eca23d7dce8e23f98c1228fd6e6d11` |
| notion:page:378e8214-84b0-81d5-a484-dc9533fdff2a | factions | Order of the Ironwing | UNKNOWN | `1386332003550c9286e3097640261b2e656df9af1bfb3c8024f91ad14c362c36` |
| notion:page:37ae8214-84b0-810e-bdc4-cbb06f0887c0 | factions | House Auvyrtha | UNKNOWN | `bcfb4c2bfe48a180d1e323cf092ab225a19240a7b8ffe8eb950d98d7c7d6dd0f` |
| notion:page:37ae8214-84b0-81c0-96f9-f2422cae98a8 | factions | Helm's Order of the Hand | UNKNOWN | `91c00bd8ecdb85817956e4335ba74ea52bb66814e6963e3edb75c32de8f872b8` |
| notion:page:37ae8214-84b0-81c8-8348-c3b0a504da24 | factions | The Wyrmhelm Program | UNKNOWN | `96afb3a4d7711a04fe5920b465e2bdcb530e61467c2a900ec31db85bf6695d8e` |
| notion:page:37fe8214-84b0-8193-885c-cadb1f4f69e5 | factions | The Moonflower Covenant | UNKNOWN | `ecaa504eb2604e3cf1543e9beae67ad908f3d858d3faaae09fdccf6b35170e26` |
| notion:page:381e8214-84b0-81c7-b992-e26deeee3b62 | factions | House Vel'Khaeryn | UNKNOWN | `949bae9ca104fa54f7680e269539cc850b92daf45115418569a04928c565e2ad` |
| notion:page:388e8214-84b0-81a3-b039-c8745cddebe8 | factions | The Low Road | UNKNOWN | `5037ae036bcfb400ab6168cccd4692fd889da6e7bcb9600e9103354b75a91cbf` |
| notion:page:388e8214-84b0-81d1-8c62-fef45e645102 | factions | House Baenre | UNKNOWN | `cca4c09d982ff168d03553055e4235e27d35d5586990287a3173a7a5a55b8193` |
| notion:page:38de8214-84b0-81db-9ba6-ef67998f270a | factions | Caledor | UNKNOWN | `6b213f57e5406304a6b8b13461709feeee3abbf3ed29492744524ad6861324cd` |
| notion:page:39ce8214-84b0-81b8-ac8f-ec8f2a679a77 | factions | The White Sash | UNKNOWN | `73acfafaee650ce5ea315146bc3087405c3c762cd5ad1d751f2657f32d7d1655` |
| notion:page:39de8214-84b0-813d-8402-dba12a5a00ac | factions | The Nine-Banner Gathering | UNKNOWN | `f5f61622712caf5aebad022ef9861f3f302795f346086188117852d4ddd445fa` |
| notion:page:3a0e8214-84b0-8112-ab84-d61039d9c852 | factions | The Silvered Passage | UNKNOWN | `b2e2160598da09a640b5b80fdd5254eb6f7c2750ae0e7b5872da06c645649ace` |
| notion:page:3aae8214-84b0-81bd-b896-f92730c67452 | factions | House Symryvvin | UNKNOWN | `4119ca42f33995184de38c74697b6259529e8de61c608d526b569f1b3a43c997` |
| notion:page:3c2e8214-84b0-8101-8d24-eb61b3e8cf2b | factions | Calimshan (Syl-Pasha) | UNKNOWN | `428cb27e942a4452b62931888943a6e88902d3f3c19442cc30c6228d9a294255` |
| notion:page:3c2e8214-84b0-8104-88aa-d07f4bded21e | factions | Lords of Waterdeep | UNKNOWN | `d629c8022a271a0d31834942ce8be9df894a346f3b1ad251a7a88e679f71e334` |
| notion:page:3c2e8214-84b0-8111-a885-e0308c1ea260 | factions | Yartar (Waterbaron) | UNKNOWN | `dc1715c6ce2287f4baef7ca26f18acf10e3017d34ee8ef31b8060f09d2e91e42` |
| notion:page:3c2e8214-84b0-811a-8961-d786dc6ec2dd | factions | The Twisted Rune | UNKNOWN | `a11cb89194bde72730294bfa58a1b8b281a7095b514abbc655d27f8b4bfc8fc5` |
| notion:page:3c2e8214-84b0-811c-8e67-d95b85323a82 | factions | Clan Battlehammer (Mithral Hall) | UNKNOWN | `5e1df5f31dff29c4267050d16e2ed2abb9e94fecfa9a09c4d07d18814549367d` |
| notion:page:3c2e8214-84b0-8123-8b13-dd743507d18c | factions | Stone Bridge Company | UNKNOWN | `4255befd6c4e1c50ac225a1f670a8275fa6d7d293156117d5d8aa4fe6cb127ad` |
| notion:page:3c2e8214-84b0-8132-9a0d-c36dd529380d | factions | The Eighth Veil | UNKNOWN | `331551e7afaa2f6eec23ada4d5e97e2de682ee3c544f6194dba47b12b8ef8763` |
| notion:page:3c2e8214-84b0-8136-ab42-e9f5e1307258 | factions | Dales Council | UNKNOWN | `cd2758b0740f7379dd1009b9017154598b2b4eb4d606ac0981de6716d46dd160` |
| notion:page:3c2e8214-84b0-814d-8b36-e5e2c932c89c | factions | The Jade Court of Aelindra | UNKNOWN | `7b5bfbd29ff0fcceb085e7eab608d29b9bd55acc1ce35115670720282aaab414` |
| notion:page:3c2e8214-84b0-8167-be0c-dfc1372ddf25 | factions | Archdevil Zariel (Avernus) | UNKNOWN | `88caffad935551590254ca04c3da127fd902bb78adf2c06ea8b8bb1aadb273f9` |
| notion:page:3c2e8214-84b0-817a-91de-d9b892517270 | factions | Hollow Reach (Sunless Queen) | UNKNOWN | `80812d8a80aec8341c44a4dbdc603e3fe22440d8a03609621f3be0e4456370ce` |
| notion:page:3c2e8214-84b0-817e-909d-f5e29072c0d2 | factions | Council of Six (Athkatla / Amn) | UNKNOWN | `807719beafb902d849ef08d15953e97c89f30ae5332e99c4edb0ac5e41abf166` |
| notion:page:3c2e8214-84b0-817e-b4e9-c028c3bb1569 | factions | Hardliner Faction (Waterdeep) | UNKNOWN | `948474f2be5dff8a2371079443ca9e3058a23469b26ae0b89a5b79e8ac807976` |
| notion:page:3c2e8214-84b0-817f-ba5d-e85463b9d240 | factions | The Heretic's Thread | UNKNOWN | `c9ebf07bb3dce268fe39f8571bd0eb3f0169c6d4bf467347d58c44a1b42b7c14` |
| notion:page:3c2e8214-84b0-8180-ad1d-d1eb2b31998a | factions | Archdevil Dispater (Dis) | UNKNOWN | `f82bbdf6ab6fa010c51523291d3c51a56c8b8ecfc585662a287347dafa94b162` |
| notion:page:3c2e8214-84b0-8196-ad9f-cf4db9814737 | factions | Cormyr (Purple Dragon Throne) | UNKNOWN | `727cb613bdba72be5d2aef7529e5ad47decc41d51501f9390050227227c90ff2` |
| notion:page:3c2e8214-84b0-81a2-8d13-e2c252a26647 | factions | Dunbarrow's Riders | UNKNOWN | `07755db7d8f40bb77d0853ef59740efe4d40f759a7166edc06fc04dfcca6b12d` |
| notion:page:3c2e8214-84b0-81b4-859e-dc0c77c36e90 | factions | Cormanthor-in-Exile (Elara's Kingdom) | UNKNOWN | `4107a337eeb35ea73b2bf7b1bd17b7d8b353b6cc8f72468641f6e885d7cbba93` |
| notion:page:3c2e8214-84b0-81be-9378-eff521f16612 | factions | Council of Four (Baldur's Gate) | UNKNOWN | `6c64ea1055b114e6dc5eaeac7d5af8136dd31f1164ca9bc169518be4d4eada5a` |
| notion:page:3c2e8214-84b0-81c0-8b0b-d1abb3bd6266 | factions | Mirabar (Council of Sparkling Stones) | UNKNOWN | `794f67cd68c58ccbe9316133bb65d47f2d6fd8e22af3f41e046fc11d12b5a3dd` |
| notion:page:3c2e8214-84b0-81c7-bc58-f1c6a4a8ae20 | factions | Candlekeep (The Avowed) | UNKNOWN | `d608de95dcb79ad6af054e9d800308df9230400ec63611fbf453919c642660fd` |
| notion:page:3c2e8214-84b0-81e3-98de-f742872121bf | factions | Luskan (High Captains) | UNKNOWN | `0dffb3142e5006c490de83a9baeb1fe9d62e94974706ffc3af7e4be7a0d63436` |
| notion:page:3c2e8214-84b0-81f2-8447-e5247b0265b1 | factions | Northern Crown Financial (NCF) | UNKNOWN | `81c01590a98976681315f638dfb804c47b29e94a52ed27d4881e885033289485` |
| notion:page:3c2e8214-84b0-81f2-be8f-d75c56502ed8 | factions | Valkia the Bloody / Khorne Presence | UNKNOWN | `ae89b04a50470be7a3c4445837194d6ef70e8f7f6278bfcce4ae31a9594e3286` |
| notion:page:3c2e8214-84b0-81f6-b3e2-eff79338929e | factions | Luruar Confederation (Silver Marches) | UNKNOWN | `78cebb7534705b32d6b81a168a91791a0e791f7fdb3f1b77a8d755343c9c23d6` |
| notion:page:3c2e8214-84b0-81fe-94fa-ef24cc392d75 | factions | Vaelthorne (Cassius Brightward) | UNKNOWN | `a398035b2d80676fb0714188004e8b75994707f3a7790b8dde2ff0d0c1d9c9f1` |
| notion:page:2fbe8214-84b0-8108-b022-c5194e50ad99 | locations | Skyreach Castle | UNKNOWN | `dd6baea8ee4db0ee9477b48ae3c39f3b0119a51f37cb4264d5940109ec375a13` |
| notion:page:2fbe8214-84b0-8131-b119-d989998baaa8 | locations | Dis (Layer 2) | UNKNOWN | `144726711cfe15e34b9f69bde6e30feae924aed8302ea8e00fec1432be275e57` |
| notion:page:2fbe8214-84b0-8166-98fb-ec6d2813314c | locations | Avernus (Layer 1) | UNKNOWN | `a56b32ae67037532f86ea24c655efebdc03b3f1ad9585bfbebcc9d6355774550` |
| notion:page:2fbe8214-84b0-8189-8b97-c6329f9f29a5 | locations | Neverwinter | UNKNOWN | `908d1d261aff5d3c17b8b2a89c8942d51ea289b3985897383b38889227a9b5c3` |
| notion:page:2fbe8214-84b0-81a1-997e-d3b747e8c556 | locations | Forgedeep | UNKNOWN | `308c5bd0f8a6c5d89d29d328bac038da792fd249c59f4f18283acfeb38f080f5` |
| notion:page:2fbe8214-84b0-81a8-8f59-cf002a2906a1 | locations | Waterdeep | UNKNOWN | `c945e6aa63016eef41dfe6d83facfcc65da67741d63be42114ff7eebe46d0c06` |
| notion:page:2fbe8214-84b0-81b5-ab0a-f9958c824b34 | locations | Phlegethos (Layer 4) | UNKNOWN | `fcb44fdd02e336f1663f9f78f3db4cfeb5c4b0824545f08d69a89bb56de00459` |
| notion:page:2fbe8214-84b0-81d9-9cdf-f3c721af0db3 | locations | Menzoberranzan | UNKNOWN | `c7d867e08948ded7df1574d2617cf968e9becd981413bb2418a441ea1f3097d9` |
| notion:page:2fbe8214-84b0-81de-b9b0-eb504f296ed6 | locations | Silverymoon | UNKNOWN | `0af95e8316531ae6b038b85c5cdb65b2ba142f92aeed8bd23250c7b6831f29b2` |
| notion:page:32ae8214-84b0-811c-a1a6-ca51e9f15677 | locations | Tethyamar / Irondelve | UNKNOWN | `d17177a3574b06e82c868204e1483028c43bd4234034d07484a0fdd23ef78dd0` |
| notion:page:32be8214-84b0-8103-85a9-fdb2312328c7 | locations | The Neverwinter Deep Labyrinth | UNKNOWN | `bef9825824415974cf6a31454c768ee0ba2d4d73f823d5865e2a7035ca25d17f` |
| notion:page:32be8214-84b0-8122-b159-f491f5f15b84 | locations | Bloodaxe Legion District — Neverwinter | UNKNOWN | `fe42aa697da527380e88328f861ac493b1a2bd55db810ce22015d0f9bed783d9` |
| notion:page:32be8214-84b0-812b-97c9-f057203aeef8 | locations | Star Metal Hills Mining Complex | UNKNOWN | `0d7f71a1899deb2b04aeb41b586a7fdadc157bdf6a5be308aedbd71408caf9af` |
| notion:page:32be8214-84b0-8145-b768-cc0f492782d1 | locations | Desertsmouth Passage — Trans-Mountain Canal Tunnel | UNKNOWN | `1d834a5b90686a3fd11cf13d6aca72c1627913f0b5d44e194a4fc5d7add276a5` |
| notion:page:32be8214-84b0-8170-b18d-de084a3d2138 | locations | Dynasty House (Vara's Domain) | UNKNOWN | `186e0d711490dc4cb74c3feaca7970713cf72d0060e7f40c675806d7defafee6` |
| notion:page:32be8214-84b0-817b-8126-e8ff4735ef24 | locations | The Sapphire Pools (Sea Ward Bathhouse) | UNKNOWN | `994505c50c536ac63c7b022243a2899ac1af1dfd276419e1ec622773a7cc0eae` |
| notion:page:32be8214-84b0-8182-a69d-fc6db5991aa2 | locations | Anatomist's Laboratory (Dungeon Module) | UNKNOWN | `b0d5d05c4cc3e6d15df0c9d69993a6fa30d3bc0bcea3d33f262cd50cc271e364` |
| notion:page:32be8214-84b0-818e-9d58-ca579f4756d1 | locations | Veil Safe House — Neverwinter | UNKNOWN | `c33fada4937c3daf01506300221f1c9ee24786c4dbf0b06b37da0560cb889b96` |
| notion:page:32be8214-84b0-819b-933e-d9b67715dea4 | locations | Schola Ducum Integrata | UNKNOWN | `e56c652814ad6994ac07b69bcb71679edacc7f004ce9622edf7ea34d30eb6165` |
| notion:page:32be8214-84b0-819f-82a4-f6eb9627aaca | locations | Veil Safe House — Luskan | UNKNOWN | `c89f61b6f42bd0f9b3c9811391d950206ac033abe4636c658a937bad21c5c6f5` |
| notion:page:32be8214-84b0-81ae-9959-f6abfdbca301 | locations | Peri's Operations Hub (Dock Ward Warehouse) | UNKNOWN | `2df9534ad3ef6529e738130e74f6acdceeb7b5b285c4b9c6b711b60220296928` |
| notion:page:331e8214-84b0-8198-a08e-e9ccb5698f83 | locations | Crystal Gardens of New Harbor | UNKNOWN | `c2914a84997b1e9be6245f63330974431da01b1367579721ae51751e7a53f49f` |
| notion:page:332e8214-84b0-8105-9c36-e6ed007fe34d | locations | Veil Safe House — Neverwinter Docks | UNKNOWN | `e385bd05928c43e442493bc6c9e77bf481f7affd774fc6a00dc8b4bf77e250dc` |
| notion:page:332e8214-84b0-8118-99f3-f652e6b532ca | locations | Neverwinter Academy of Natural Philosophy (Devil Academy) | UNKNOWN | `8c7fc6af7ef0c972386abb9c0715a7e93681f8a3194decf7a911733ce2f263a2` |
| notion:page:332e8214-84b0-8121-82d7-e120098fb69b | locations | Collegium Montis Gladii | UNKNOWN | `2915286d2e803ce1136c6378c806ad41ece6a45877e375084363a01343baec8b` |
| notion:page:332e8214-84b0-8126-8f9b-d7f0c40c8ea9 | locations | Orchard Chapel | UNKNOWN | `cfee1b16aefcc4464289e08690d19ec876f0137c28a2117a636ac7ede4827351` |
| notion:page:332e8214-84b0-814a-8efb-de14fadbbd21 | locations | Venetian Bay — Premium Waterfront Development | UNKNOWN | `40d33e3ac036487faa9fc66567e210eff64e13c14cd95deaae4ef033bf1f74ea` |
| notion:page:332e8214-84b0-8168-baca-d2c113c751b7 | locations | Shield-Copper Plaza — The Comfort Plague Memorial | UNKNOWN | `b30c46aff930a2e352e84441899c1ca95a14ef175d9ce0f95fd4cb8077c64123` |
| notion:page:332e8214-84b0-8190-86f1-e0f98c7c3298 | locations | Dock District — The Baen Quarter | UNKNOWN | `03982771ad9166b00e4e0293d26a46370d236b9e4468a6c29ccdc68d17061bf3` |
| notion:page:332e8214-84b0-81d3-bb13-f54b12daf00d | locations | Neverwinter Working Docks | UNKNOWN | `ef8f293f20f82bc2a16d4ee26280af5c7f26d417baa370729cd0b3ed3b9d0bc1` |
| notion:page:333e8214-84b0-8120-a75e-f11a243ab6d5 | locations | Baen Northern Industrial Yards (Warborn Production Neverwinter) | UNKNOWN | `f592544cea3f2631b12c1f4ab9a12b1cb7bad44151f4f04ad3c9285cf51cc20a` |
| notion:page:334e8214-84b0-817a-bbc6-d240af9b9d00 | locations | The Foundation | UNKNOWN | `82f07ce120925e824e0342467393340e0ed400a6e6198f9dafc6d695cf1a0c1d` |
| notion:page:33ae8214-84b0-8114-9c37-c6f48cf2f139 | locations | Northman's Cairn | UNKNOWN | `7c043ec0a242320814168ab66720a91d2082737a30668355e76e1dbb5c8f96d4` |
| notion:page:33de8214-84b0-8152-a773-ce4b13c010d3 | locations | Dunbarrow's Hilltop (Greypeak Foothills) | UNKNOWN | `df8b0e107aec5ad64ccc3e0b12d241cd76e14d82a24bbc0b7baf4f5be001fd7f` |
| notion:page:33de8214-84b0-8191-ab65-da92a203b331 | locations | Chauntea Temple Ruins (Stone Bridge Company) | UNKNOWN | `6171782694a8050ab37e0bd3792915ceed22c40e0de38f35f9e09b60895b1bd6` |
| notion:page:33ee8214-84b0-8139-b02c-e643bdb0b08e | locations | Karak Durath — The Underhalls | UNKNOWN | `291bf669c57b406b5d12e9fc9e0a46bbbcb4c65cce5ec942a59d74bfce86e5d2` |
| notion:page:340e8214-84b0-8120-97a3-fb2bfe099b18 | locations | The Soul Forger's Repose (Moradin Shrine, Karak Durath L3) | UNKNOWN | `9de9b620d56a789d7ec7d53289c89c956870fde0085412661b3c248d07b91df4` |
| notion:page:340e8214-84b0-81a3-8bd6-fe7df84566de | locations | Ravencrest Estate (Surface) | UNKNOWN | `f70241e66a40338d6249da6b9292a92ee820f1113ddef828bd3165800dab3227` |
| notion:page:340e8214-84b0-81aa-8867-cb57d9730332 | locations | Fellowes Hall | UNKNOWN | `721bda9f29386ee2f5101c70fdeccb54d78aee2e8ab944854afb7ebe7a1f3b4b` |
| notion:page:341e8214-84b0-81ba-97e0-c8e16ed2cc23 | locations | The Gilded Sparrow | UNKNOWN | `410598cac9ee7f2795287461278ee0005737cb50b70f9a9b69616dc6bc587728` |
| notion:page:343e8214-84b0-8189-acca-dbcdefeb2bc2 | locations | The Windcaller's Roost | UNKNOWN | `7b2b8e112513a7f60a60bbbc60b33282e18471fc2fc1819b5ebe0add623ee54b` |
| notion:page:344e8214-84b0-816d-bd56-e1308c52a6f6 | locations | Pelham's Grounds | UNKNOWN | `def5c79e9db245cb2ab50073a5e98f73658d089a0ebee948fc0293c3178d9b74` |
| notion:page:347e8214-84b0-8130-aaca-cba4e0320d9a | locations | 14 Blackwatch Lane — Baen'und & Dior'elle Showroom | UNKNOWN | `2cc0a11ab0044fbc55a6e73edb620cf77f6a617688c1180e2c595879d7409767` |
| notion:page:347e8214-84b0-8142-a46b-c164ca8aeaf0 | locations | Celestial Compass Estate | UNKNOWN | `7cff2bd328a1c7a1051666e824989f12836b0bd787fcc1a2bbe137d680fb4aa8` |
| notion:page:347e8214-84b0-814b-b10e-f27635d0da69 | locations | Angel's Fall at the Devil's Gate | UNKNOWN | `0ec35b07d85960d2e702ac0fe06c709d8588ba64c2f416c1f4be9e7887a20f18` |
| notion:page:347e8214-84b0-8162-b8fa-cdfa7b0b3e3e | locations | Candlekeep | UNKNOWN | `e64ce4fd644623c58180d36aaca96bfcba1c280412def5e7086600982270e1eb` |
| notion:page:347e8214-84b0-81a8-894d-ebd644477ba1 | locations | Institut de Tissage Arcanique | UNKNOWN | `3e18a070efe36b26ca3f4865eeca47f96423d6e4d031097317401a8638fe1567` |
| notion:page:347e8214-84b0-81b7-9a99-f4016179ac7f | locations | Commerce Court — Trades Ward Judiciary Annex | UNKNOWN | `80e8eb817d300e5b18af809ca7f49cd0f9c206f84001ac5f7f17bcfc932b343e` |
| notion:page:347e8214-84b0-81e5-832b-d95fcf00b2d9 | locations | Millbridge & Millbridge Merchant Trust | UNKNOWN | `295e9fcae56358f094f5edcc13481f1ef14ab55c7786387c455b0dfb0a63ef71` |
| notion:page:347e8214-84b0-81ed-bc20-e48766ef4f7a | locations | Silverhair Artistic Metals | UNKNOWN | `af24c47d0ffdc4408d422457bd38945f9f78d56ae20ff56bbc680bb8b55b4809` |
| notion:page:348e8214-84b0-8100-ac1a-ed6b31fbe41f | locations | Elfstone Tavern | UNKNOWN | `ab5e14639ca77e254aad2132e7189b2107f312efa88d7342a2746a3b31a87676` |
| notion:page:348e8214-84b0-8102-b0c4-e69d4dd2197c | locations | Stoneshaft Hold (Thornhold) — Dwarven Clan Anchor | UNKNOWN | `d11177518e96702ed044733f2a4f78f53f73413029070fb6b44c461da7662775` |
| notion:page:348e8214-84b0-8103-b73b-f7df3fb8cec5 | locations | Guardian's Gate Ziggurat | UNKNOWN | `6eb530d53f47f6c032c479ae8eafab4fb345b994ebb1b00a18938a0a97be39e9` |
| notion:page:348e8214-84b0-8110-8dc3-dfd9aae048a2 | locations | Nethpranter Street Dead Drop | UNKNOWN | `4eefd349efc5053e6b24fe641be09591a067c9e0e0b89109e9dcd42f3519b11c` |
| notion:page:348e8214-84b0-8112-b40a-d344a830c40b | locations | Mount Waterdeep | UNKNOWN | `d892c155b24332fa20812a2d608f9dcabb31afe0fd2ebadd6c1df2f36db63dd3` |
| notion:page:348e8214-84b0-811e-81ef-e10c205dbb70 | locations | Nessus Library | UNKNOWN | `839478ebf4fc3002415d55264904d7156245283206d8f246b17145c0219e34a9` |
| notion:page:348e8214-84b0-811f-8e80-cbd2eaf87662 | locations | House of Gems | UNKNOWN | `28de2a6053f457cd0d9606190efd30a207c9c9ad8e8d41ac91a4990adc7e668a` |
| notion:page:348e8214-84b0-8121-8429-ce992005d5b8 | locations | Seatower of Balaeros | UNKNOWN | `51d283888be8c725ea6cb6f6ab8629162f4214b8fa7bc77f493201d6630f7ef5` |
| notion:page:348e8214-84b0-8123-bbb5-f856b260a8e1 | locations | Skullport | UNKNOWN | `736cd8e1ec4ce50bcfbe7f57bf35234c418c6013569336bc016a29e2754ab4fd` |
| notion:page:348e8214-84b0-8125-9d6b-ce13587ae431 | locations | Moonwood | UNKNOWN | `f7768170283b91b13bab3c419a3197711afa6bd8bfb521c12568c1e54af92b70` |
| notion:page:348e8214-84b0-8126-a246-fda30898b68c | locations | The Atelier (Baen'und Original Workshop) | UNKNOWN | `ca1bf0016c0903545f0b6559b6a2f320ec69c0e7ebd35f19ff7b3ff1619390d6` |
| notion:page:348e8214-84b0-8129-900e-df135c620093 | locations | 14 Nethpranter Street — Holding Cellar (Observer Network) | UNKNOWN | `bc09e5790a743eca8531078f1a6603a894f96b9583cacfbf345016d3ff98658a` |
| notion:page:348e8214-84b0-8138-bb0d-e9c71c8bfdc6 | locations | Blackstaff Tower | UNKNOWN | `d58f88385bb298dda9dfb212f3a4b3d8d9ac1e9daf84d44dd32e6a1da3588bdb` |
| notion:page:348e8214-84b0-813a-adc6-fb73af67e2ea | locations | Cormanthor | UNKNOWN | `f7437e8a7abb42c91ef6677717e85c6431d2dded351bee9abc0cf60bb8d083e9` |
| notion:page:348e8214-84b0-8141-8aa0-cd6be66f5986 | locations | The Yawning Portal | UNKNOWN | `c2eddcd8a32ae72d340ce237ba0a1ae67e39afdd51d6743fab1d557cf4142bcb` |
| notion:page:348e8214-84b0-8144-bba1-f2885704de1b | locations | Crosscurrent Inn (Neverwinter) | UNKNOWN | `43ecf64f2a35e3247db88c78d3b924ec61c5e2b7c6fbbe18851baf415575fcad` |
| notion:page:348e8214-84b0-8147-a51b-da9c6feb22f5 | locations | Font of Knowledge | UNKNOWN | `ff90a33ebae84d79e002579cb62807d41e2631bb809dabf0073ae68ff61593bc` |
| notion:page:348e8214-84b0-8149-a7e3-df762f727510 | locations | Lamplighter Guild Hall | UNKNOWN | `59bded9aba0a6fd32413a3a64395a3c9bc3a0d94d60be4b77799bd3d34e069e2` |
| notion:page:348e8214-84b0-814c-b161-f14dcbee9632 | locations | Mistshore | UNKNOWN | `baa6cd90d73ed132ba4e7b5c619662d55c6cb2524fbda20062796b3de0874ef4` |
| notion:page:348e8214-84b0-814d-b068-e0de417a0020 | locations | Husteem Distribution Channel (Noble Circuit) — Waterdeep | UNKNOWN | `4403dc33a495afa2fc522e74961f7c2be0b77df58c2cd87fe97e3ed73440a051` |
| notion:page:348e8214-84b0-8151-9443-cdeb31108009 | locations | The Plinth (Candle Street Dead Drop) | UNKNOWN | `551732a2de25dcbe15c0f27404d7f55ae88c13fe3dbda3b6a00521397224bd1f` |
| notion:page:348e8214-84b0-8161-8afd-e2e826b898e1 | locations | City of the Dead | UNKNOWN | `3d0ab29b1de2b0d0b8cf68d005d7c44a2dc415a3eaf0f494ac7f07bdb931e0f8` |
| notion:page:348e8214-84b0-8162-8111-fba51071e587 | locations | Hunding Canal — Baen Continental Waterway System | UNKNOWN | `5e4ecb27040594aee12f303ae3c3f33def0724039dbf246a712cced6c8dff1f8` |
| notion:page:348e8214-84b0-8165-8ce7-e0639959dd20 | locations | Fish Street Receiving Office — Luskan | UNKNOWN | `6d7dfea28766f0eb2090a67575e0973c63997e8bd5cabc2b15111b0770405743` |
| notion:page:348e8214-84b0-8170-a5eb-d6a99b8bf748 | locations | The Walking Statues of Waterdeep | UNKNOWN | `3045be378a146967678c4f9d3b5df1b417050b34bcd6f98e0d89e4dd891d2687` |
| notion:page:348e8214-84b0-8175-9eec-db1f9a0dc720 | locations | The Blushing Mermaid (Firth Briefing Tavern) | UNKNOWN | `693c73b53b450fc68c5ad2d074896af6a0f6ef5268940ae6fd1f92576c21a1f1` |
| notion:page:348e8214-84b0-8175-a565-d27c16e5e1b5 | locations | Cerulean Circle Convocation Hall — Neverwinter | UNKNOWN | `db945fa7adeae9cd9c2033df123b72678d24a71358bbfe879e2806f9457d6b2c` |
| notion:page:348e8214-84b0-8178-84b9-f537ea3bf11b | locations | Rosznar Manufacturing Facility — Waterdeep | UNKNOWN | `9c10d416e39c55d98e1fec0e2ee3060393079126b581fd3617561a3601b239e2` |
| notion:page:348e8214-84b0-817b-b87b-c053573a5596 | locations | Screaming Cliffs | UNKNOWN | `28858b182d9638fbf5ab7c51b0e31193fe4bdada18b8726323f29ace7f08cf63` |
| notion:page:348e8214-84b0-8191-bda7-d7037f891811 | locations | Amphail Waystation (Dessarin Corridor) — Acquisition Pending | UNKNOWN | `bf04bc2e9c19950a9ea7aa1bb3aead826c4e2e88a3de531f22339e3657d2e8e8` |
| notion:page:348e8214-84b0-8192-95d8-f81988611e45 | locations | Waterdeep Warborn Mega-Facility | UNKNOWN | `25886350c7963fde3ebd33bf6339dc6a13f751957a35c910352edaf6063d4110` |
| notion:page:348e8214-84b0-81a3-b119-cb252796aa61 | locations | Baen'und Component Factory Site — Neverwinter | UNKNOWN | `6cfe80561caad2e46450524c7abf7aac683fc0f3879609d2c98df49c26edf3e3` |
| notion:page:348e8214-84b0-81a6-8349-ecdc1f0efef8 | locations | Longsaddle Valley | UNKNOWN | `bf0245b7c4de1cf4076f4cda2d5cfebdec038f39d5893bf6bcbfd48ca21f0b05` |
| notion:page:348e8214-84b0-81a6-907c-e3066551f69b | locations | Aldwich Lane Workshop — Neverwinter | UNKNOWN | `e9c529474aed41cf7f86166200e49a6f0b69c145aa57ff6bd22d88e10f95e9dd` |
| notion:page:348e8214-84b0-81a8-a8dd-d69c21b5f1b5 | locations | Undermountain | UNKNOWN | `2baa9996bde27f8cd125a1b51bfd45e13fc6a95fd0a96e927dc3ec24a7934b28` |
| notion:page:348e8214-84b0-81b0-810b-dd2083f0362f | locations | Baen'und Innovations — Waterdeep | UNKNOWN | `ebf7fc526dcca52534110ddb223c657e7b2703ff04de8d705aa7592be38d2959` |
| notion:page:348e8214-84b0-81bd-a639-ef5dd4981b1a | locations | Thornfield Estate | UNKNOWN | `d6e824ff187bac5ece29e8b30c64237e99c320ae95aa907450a7b1010f474a43` |
| notion:page:348e8214-84b0-81bf-9ce2-d3a58b2310fe | locations | Castle Waterdeep | UNKNOWN | `d2984a4f1739f544d0bc2c4cad07a659e24ff1b0c3ffe1b484ded2bc4880f5db` |
| notion:page:348e8214-84b0-81c3-98aa-ef7a40cdd803 | locations | Deepwater Harbor | UNKNOWN | `65f138fdd7d229bf2a1b5500a2032a0878da76b587f8d8e059b92b366be931d6` |
| notion:page:348e8214-84b0-81ce-8378-ffc93d9bebf2 | locations | Inevitable City | UNKNOWN | `385169928f32682da8112402fd56846eb6feab66f31a826b7391df50ca4f0edc` |
| notion:page:348e8214-84b0-81cf-96a3-e3a18af78c89 | locations | Toril Shield Assurance / Securus Cafe | UNKNOWN | `f2a485f7fd0f0e7b6ffdb61bb5e59bfcd4edc136a5e0e96e296bfedbce5698b6` |
| notion:page:348e8214-84b0-81d1-b5d6-ce4274842211 | locations | The Market (Court of the White Bull) | UNKNOWN | `a9cc6dafca87db8da58ce121b2ecd95eaae3ce51fb4c4b3d86a05fd9776724a4` |
| notion:page:348e8214-84b0-81d3-ba53-fa0ef760543a | locations | The Ledge — Dalelands Corridor Overlook | UNKNOWN | `e748c033475292b532194d24f53cd17202d95678daf37514d0188763e7195930` |
| notion:page:348e8214-84b0-81d6-92af-ca37333dc5f3 | locations | Gauntlgrym | UNKNOWN | `ccdd02c4b348f62114c1391aeb99aa40d84686bff06c25b02c3b9f976e20aa35` |
| notion:page:348e8214-84b0-81d8-b39b-d2d00f403644 | locations | Ravencrest Hall Program — Baen Construction + Treasury Quarries (Day 729–1200) | UNKNOWN | `445c981d3a98cae4bc9ef3173f6b4983b42982ae9dc68ff85d68d324f60691a7` |
| notion:page:348e8214-84b0-81d9-a53b-e4d73450d2a7 | locations | Tethford | UNKNOWN | `3e987c594bb8b60ae8d61c140fcc4b9394b041284dc06db5bd84f71d0a233dee` |
| notion:page:348e8214-84b0-81e0-a1d3-d90902c395f4 | locations | Yartar | UNKNOWN | `0093374d02a99bc35c0bd73fb905523be8ab1052cf26a9fd01a3b8528c9f2556` |
| notion:page:348e8214-84b0-81e2-a79d-c3eb294ee1f4 | locations | The Saltcellar (Firth Secondary Meeting Site) | UNKNOWN | `e98b52bdeffc8f436d4f8bf81823041a02bb53ce0b3cc3472c5d196edce162d1` |
| notion:page:348e8214-84b0-81e6-b8e3-d5334331bc22 | locations | Old Xoblob Shop | UNKNOWN | `d86c7ba9319478f3e57d2af553dc813167d90ce6871b4b0cd558754da0b949c4` |
| notion:page:348e8214-84b0-81e8-8a9d-ca14db3e72bd | locations | Mithril Hall | UNKNOWN | `8f72221d3c8ef0a40d477f813bf2c9eaeadf7c2d7952c15f952b3ade7a43ee8e` |
| notion:page:348e8214-84b0-81f5-9495-c4fa7ee5c086 | locations | Rassalantar Waystation (Flagon and Dragon) — Dessarin Corridor | UNKNOWN | `dafbf7714ddbbac587bac962f6e267a8b629f119f2b738d2a45355b62faea76f` |
| notion:page:348e8214-84b0-81f7-9f8f-ea8c31905f65 | locations | Northern Crown Financial — Castle District Branch (Neverwinter) | UNKNOWN | `99e62b5dd43296fc49324355ea56008a3da6f2b5c930f9f6bf1ece27ec2c8a66` |
| notion:page:348e8214-84b0-81fc-ab24-cad55e8da100 | locations | Petra Voss Laundry (Candle Street Cut-Out) | UNKNOWN | `0b679de396bef824f6686824a4abf5cc2a1c67f998184e5d54bf5f105dadc1d1` |
| notion:page:34be8214-84b0-810d-88da-c87a2a6c5e5e | locations | Haulver & Cray Notary Side-Room | UNKNOWN | `f11c3256d3153cad165ed4b73ed19d0223800ad392f88565c1f7e828ae73ad5e` |
| notion:page:34be8214-84b0-810d-946d-d27352f7df76 | locations | Ironside Boarding House (Anchor Lane) | UNKNOWN | `02a86446a5422191de8c54e773840bfe429d5817fd91d22abbfd36ec8bbc2fee` |
| notion:page:34be8214-84b0-811f-a74c-efdfc7e6d2aa | locations | Greymantle Alley | UNKNOWN | `955e843c42992b2b7e8e5fba0d6655365a69ea3c009768d88addcc9d7f8805b8` |
| notion:page:34be8214-84b0-814d-8b94-c755aff46399 | locations | Ashwell & Merrith Commercial Archives | UNKNOWN | `b7cda806b2af96cc9f252255b0584dd230c4ad74f76f6371fb9082d06fd6b864` |
| notion:page:34be8214-84b0-8157-b4ca-d00d6b8a9107 | locations | Tull & Hadwick Bonded Freight Yard | UNKNOWN | `2af3afb2b8fc43d99d48d39af74621d0c4772731fea0e310ed8f63f4269eebd4` |
| notion:page:34be8214-84b0-815e-92aa-d44c0e72913e | locations | Cordell's Reading Room (Selduth Street) | UNKNOWN | `66533f3c444d87e6b0960768ae0ea8c7338b9d9d524c644bc4c8feecbe7fb4b6` |
| notion:page:34be8214-84b0-81a4-9941-f02a691409b5 | locations | Verandine Private Chamber | UNKNOWN | `5ef72ae2f4ee8f6cfe2778383c1e30fe7e42c41d2d1a8ca4e1141549219246cc` |
| notion:page:34ce8214-84b0-8116-b30f-fc437701a31b | locations | Sembia | UNKNOWN | `f359d58fbcac77112e0fdd6b64ff1fe722881a191026ec1d735ac4e7bd6cd422` |
| notion:page:34ce8214-84b0-8119-a8f4-e7cbe9ab9375 | locations | Dock Ward Warehouse Node — Waterdeep (47 Herring Lane) | UNKNOWN | `db1db93b92147eb9a7566710800e1db0b2e7ac2d0274b8040688a374890fe412` |
| notion:page:34ce8214-84b0-8121-ac2a-f6b56634769a | locations | The Cerulean | UNKNOWN | `8ce99944a07999ea6a0f1bd6825ac25d5dee1de254223093cf7ab063a0030a68` |
| notion:page:34ce8214-84b0-8123-b128-f25c130c0e69 | locations | Veil Docks Facility — Neverwinter Physical Operations Node | UNKNOWN | `dd699ff437e6bd209d069b4446b90896bc93a90fd9064aa36be7cfcf53738daa` |
| notion:page:34ce8214-84b0-8137-917c-e3c16e60d2da | locations | Calimport | UNKNOWN | `e6b273c63bfbae350cc091d205350654d59077ae5193af957a813ea6907db67e` |
| notion:page:34ce8214-84b0-813a-b762-f0810714306b | locations | Maltheus's Laboratory — Three-Level Research Wing | UNKNOWN | `56ff5a4efc40f24185dccd5d3f130c43bad077f7e5abe4232c9d7691b8bb3988` |
| notion:page:34ce8214-84b0-815d-97ac-c2ffe6144340 | locations | Suzail | UNKNOWN | `ee8b27c2dc91f884666974bff5f737ca9d12ba16b71f4c6e290ec2eef906afdf` |
| notion:page:34ce8214-84b0-815d-aa7d-ed8836079200 | locations | Luskan | UNKNOWN | `f8c2e792c35acc89a1d808c60fbf670a996a3d015f09cd8ecb415eae857b2091` |
| notion:page:34ce8214-84b0-8192-a3e1-d7a8e01f59ab | locations | Celestial Springs | UNKNOWN | `d074b28779406272ecdf8b868ed3dbdf259755e779befc39de7715698ddfd494` |
| notion:page:34ce8214-84b0-8194-8b0d-c5bd4ef21e14 | locations | Dalelands | UNKNOWN | `2763fd7f05fdc0f7e82be0c7cb508f5688605d690cf378dd7fcf79fcae71d89e` |
| notion:page:34ce8214-84b0-81a2-971f-e07cee60db41 | locations | The Shadowed Passage | UNKNOWN | `294b0bf3c974f2cddc14465dfefd65ce0de63ea23d11bb281ba16f0932f5bb02` |
| notion:page:34ce8214-84b0-81ae-863b-ee660d607219 | locations | Waterdeep Trading Office | UNKNOWN | `7bd24e746a6b8a94dad4d28241cc8ea9fc10de93ee5e3d006e6ce9ed04f81dc2` |
| notion:page:34ce8214-84b0-81b3-8852-d7e57a7ddc60 | locations | Verdant Cascades | UNKNOWN | `e984a4d499859f8f7da05fe26ae511d3a2d1f9bb6f510ed845cd6bd6f7ef4fad` |
| notion:page:34ce8214-84b0-81b4-80a1-f21c1cf84b7e | locations | Baldur's Gate | UNKNOWN | `c97454e07d621470ab4eceb26121ffa0f5d6321d3f2824047ab901799c11d02d` |
| notion:page:34ce8214-84b0-81c2-ba0f-e0203fa2676f | locations | Thirst Glacier | UNKNOWN | `46c6c09ec27a53659a69d33ba6ca030cdc071c5e714074f916a66adf2041b91d` |
| notion:page:34ce8214-84b0-81c8-a70a-cb6d6e6713ec | locations | Athkatla | UNKNOWN | `8ef1e06a26dfec197c9f4f6a98c826ceedf0f2ed4c18da52e6794b43f589b741` |
| notion:page:34ce8214-84b0-81c9-87b5-eb42379ee215 | locations | Warden's Vigil | UNKNOWN | `499d0c0fdca56fb62fabaafdc9569d7fdef997a461d89332b3b21310972c7b1c` |
| notion:page:34ce8214-84b0-81cb-a456-df180208d010 | locations | Thorn & Silver Exchange — Luskan | UNKNOWN | `80f1063fe68ea483c8fefbc9ea3fab1c2b71f0c9cff2a9bcc7f808ddafa922ed` |
| notion:page:34ce8214-84b0-81d0-98d8-e1b1967a5188 | locations | Safe Harbor Inn — Luskan | UNKNOWN | `e102e2b26fd0517032ac94979fb2172d9882ef9c1d1f801e6973e9f193038c26` |
| notion:page:34ce8214-84b0-81d0-b826-e05d9ac43342 | locations | Mithral Gate (Proving Ground) | UNKNOWN | `2b4580ef824d7d5be2483c2a50ba7dd53834f8c105635f407ebf2bbc73caab61` |
| notion:page:34ce8214-84b0-81d4-9ba6-f0ded0305137 | locations | Baen Continental Waterway System | UNKNOWN | `3e365b8b22642edfaca275233b695775c31d92251f5cccdf1eeb929b0d9d5c49` |
| notion:page:34ce8214-84b0-81de-bbfc-c4e4aff3134d | locations | Mennarn's Folly | UNKNOWN | `4b819daaa987d4fbe37a41c35ba8622af853b8b4f46ec3ef92d41969f4c31ae5` |
| notion:page:34ce8214-84b0-81e8-afe4-c305db68a0ab | locations | Baen Settlements — Gauntlgrym Road & Dawnwood | UNKNOWN | `003e14969f388b92e6eba2d95ff5c98e2e0aac69360cc803dba9fb3c787ffc4c` |
| notion:page:34ce8214-84b0-81f4-9f96-e13329a117c6 | locations | Anauroch — Eastern Region | UNKNOWN | `b124596247d5650f10bed5102365edf95e41643911f6131e0c69faec7f23deb9` |
| notion:page:34ee8214-84b0-81cd-adac-d7764adfcc6a | locations | The Hollow Sun — Aurixalnar's Lair | UNKNOWN | `f87ee12682de2befc609f5125de2e941427819136d1d9ff81bedd0ff9014877e` |
| notion:page:361e8214-84b0-8108-98c6-c6ab45d6ae2b | locations | Northern Crown Financial — Luskan Branch House (Shipmaker's Row) | UNKNOWN | `38ba0277b08a2deb3b919adaf57659a1137a9fd92d4fc7991ebc43a6be22df28` |
| notion:page:361e8214-84b0-8114-927c-c6436632eda6 | locations | Northern Crown Financial — Suzail Branch House (Bardenthal Counting House) | UNKNOWN | `dccc5039212733c18a693455b12a9d69233fca306e5d911f344ba8fc06802b4c` |
| notion:page:361e8214-84b0-8146-a17b-cbbc1d829c97 | locations | Hollow Reach (Independent Polity / Anticipated Vassal Kingdom) | UNKNOWN | `f0433eeda72dc1560557246c9dd1b50c1b6b93e7cd6796801da61cd7bf909145` |
| notion:page:361e8214-84b0-8147-bd70-cf207ddfefd2 | locations | Northern Crown Financial — Neverwinter Branch House | UNKNOWN | `54be8934a06bd5afe81915aef3ce25cc92e3a500fc02227b2f41ad27168c91bd` |
| notion:page:361e8214-84b0-8154-9abb-ff2fba3cddea | locations | Glacier Terminus Complex (Anauroch Glacier / Fortress Lloryk / Eastern Canal Terminus) | UNKNOWN | `a81377977c1bd3bfbcfdaf1d7081ffb6284fe6db9c3239bb47cd56b2c3642103` |
| notion:page:361e8214-84b0-8167-8d69-d9adf9e2b5db | locations | Eastern Anauroch — Frostborn Legate Region | UNKNOWN | `0508a3b88328a1ea043bda6fad6cffab5b6056b6e70d627288008006bbcfa656` |
| notion:page:361e8214-84b0-8178-811c-ea3b87b98886 | locations | Akhet-Senet (Sun-Crowned Heights Plateau, Thay-held) | UNKNOWN | `90040bdc4f14830a37a6dbe1227690c045fb5201d0911b18843c09ac994b3688` |
| notion:page:361e8214-84b0-8178-a028-eef9ba893773 | locations | Northern Crown Financial — Waterdeep Branch House (Trade Ward) | UNKNOWN | `4c4921fa143691f9a7a235e9488e1f5717bba4e559919100e776d7f72bb7588d` |
| notion:page:361e8214-84b0-81a6-af8f-ffc95216b2e8 | locations | Akhet-Sereth (Ruins of the Pre-Trouble Mulhan Capital) | UNKNOWN | `91ebf5d65b429c8d9eaf6607a94f3ed0a79b330f0be49b434a1faeb8d88449dc` |
| notion:page:361e8214-84b0-81c1-8106-fac55527195c | locations | Sethr-Anhepet (Capital of the Hollow Reach) | UNKNOWN | `47247207f372fda1e996435026c4ba3cf9f7e6d37a2fdb4827adf534c4657e20` |
| notion:page:362e8214-84b0-8146-9996-eada540f9dd9 | locations | The Faske Library (Discreet) | UNKNOWN | `c0b1e832e18a4e920a04f9785a7bce5b4364f08873cbcb8c3d27f014d93e2471` |
| notion:page:362e8214-84b0-8166-89cc-cc72eb8dfe59 | locations | Faske & Halloran Premises | UNKNOWN | `fe09872156f9eb6d222c59358d669920e808ed2a8684b10f437bc0c18a2e25e0` |
| notion:page:362e8214-84b0-81c6-b58b-cc3e9d78094f | locations | Halloran-Faske Townhouse | UNKNOWN | `b8dfa79f1180180626bb15732d1c3ce3e301b3d7a531b686803459f76eba73f9` |
| notion:page:36ae8214-84b0-813a-911a-d8b205c76a29 | locations | Rimehold Cloister | UNKNOWN | `9d031860a212c01a118effb1a651e68381c785b0a80fba4e156fa26047cfea64` |
| notion:page:36ae8214-84b0-81f4-b34a-f63c44327bea | locations | Talvert's Ford | UNKNOWN | `636779d102dc4cf43ce2d91a7b1b23c454dc3da008858d4e7502eaa3066be82c` |
| notion:page:36be8214-84b0-8174-bdf2-f22d3e43e403 | locations | Maltheus's Laboratory — The Concordance, the Theater, the Standing Problem | UNKNOWN | `d26f93c43c2b7fdf8df74b516f57a95965080645ac733adf7f7f050b912ddd1a` |
| notion:page:372e8214-84b0-8153-8a4d-e3076e917016 | locations | The Vast Swamp | UNKNOWN | `28767c11d77574f54bf5b51154fee7b3e88309790b6e4327b3c2568188d838b4` |
| notion:page:372e8214-84b0-81e9-bf93-e7a587e13fba | locations | Selgaunt | UNKNOWN | `934632918a52edbf5758934ef668290db64b87170dfd9fec4e0f561b35f3bfa3` |
| notion:page:376e8214-84b0-8156-ba5e-c9cb80aa57a4 | locations | Khem-Ruur | UNKNOWN | `b00a77b1e1fbcbb3e802ae7f00bc8ccf4f07750aa4a6efeb4b4a83bf1089fa34` |
| notion:page:376e8214-84b0-8195-b319-fbd85aa359b6 | locations | Northern Sea Gate | UNKNOWN | `c29bdd17050710a2784e88bfb633ca962bbdf3e42e944c1bc8baad2819a52c31` |
| notion:page:376e8214-84b0-81c4-98fe-c09d23b01898 | locations | The Seven Spires | UNKNOWN | `184816d2f45bc89df0071e98ef50bafafa9886342d8ef08b898516c04c4c9289` |
| notion:page:376e8214-84b0-81cf-b7a0-e6a0aee7a57b | locations | Fortress Llorkh — The Water Throne | UNKNOWN | `f4bd210de942ba109539806670319ca90daa32546810a4a0ceab8cf932c84af6` |
| notion:page:376e8214-84b0-81f6-b91b-ea0dea73e916 | locations | Loudwater — The Venice of the North | UNKNOWN | `39b8f5b7cda12afcd0098a832bf1468b0ebdf6c559af0de8105db7001073addd` |
| notion:page:378e8214-84b0-81ee-aa0c-d2792f860cb7 | locations | The Saltglass Baths | UNKNOWN | `3e3e551e509eb5004a3f242be86da49798a8a8eb54db29933a76ea236f590e23` |
| notion:page:37de8214-84b0-8138-8622-e02dcadce4bf | locations | Treasury Quarries | UNKNOWN | `20a4db0aa1e2908cd69b028d4ee3eb941b1a6248e1bada0ed175069683a7933b` |
| notion:page:383e8214-84b0-81bd-b71c-de6bec0780d0 | locations | Akhet-Senef (Ruins of the Sky-Veiled Capital) | UNKNOWN | `e1ad99e20365a580a45cac7868d9c2895f2cf4021f2238dbb9ddd8fe5854d41a` |
| notion:page:388e8214-84b0-816d-ab3a-e40ee4aaeb07 | locations | Sildëyuir | UNKNOWN | `45d6749f9b902474f800e1b2c9177e0a896128aef8664869ca05458ae7d383a0` |
| notion:page:388e8214-84b0-81d8-af7f-ce75f6e3b5bb | locations | Tir'in'tiral | UNKNOWN | `120b253cc1632483b5ab20f26a26a53c186259285a24f48c6b8d82a0d00021dc` |
| notion:page:38ce8214-84b0-8191-b531-d89b2ade8198 | locations | Trollflow Redoubt — Forward Observation Post | UNKNOWN | `64c3a49e46649904ff00551699cff62cf58f626c251bd0069835d44d428f0ac8` |
| notion:page:38de8214-84b0-811e-84bd-d2a4ae725a54 | locations | The Junction Waystation | UNKNOWN | `e2e52b07c55a9f1825a8bfbf40729605db8bac4763964c574c3c0aed3bfa9840` |
| notion:page:38de8214-84b0-81e1-b9ac-ea69b2346a24 | locations | Surbrin Eastern Road (Baen Bypass) | UNKNOWN | `cee2cd26037be6dd09073a032180b2d5f0195cc682e3acd8fcb06274b4ed0d82` |
| notion:page:38de8214-84b0-81f1-8e13-f05afbaba879 | locations | Isle de Troll | UNKNOWN | `1467b0d94722ff8757fa13c9ed012a7476af305760ee07c654cfbed431301eea` |
| notion:page:38ee8214-84b0-81fe-9a92-e8020a7be7a8 | locations | The High Forest (Caledor Domain) | UNKNOWN | `f941117ddba51a491235f99588648543ce860c5f69308c343f1117a677d9aafe` |
| notion:page:392e8214-84b0-819b-9878-d48ea5b1dc44 | locations | Mirabar | UNKNOWN | `b67ab71997f2b99430264f81d1c038ef3e916d33017bbde3f789ccc445a19ed3` |
| notion:page:399e8214-84b0-81e8-a738-f93f1e833aeb | locations | Inevitable City — District Gazetteer & Hell-Quarter Ledger | UNKNOWN | `d6cf76fb06484042f4b4d758a4c8223d3fafdba59c97c49e0480d4c481d6986a` |
| notion:page:3a0e8214-84b0-816b-879a-ce1e87613511 | locations | The Deep Galleries (Delve Gate) | UNKNOWN | `dc768c464dcce1694c6316182f6b8b4db103b9a57fbbeb4043352e60af4fe354` |
| notion:page:3afe8214-84b0-81a0-9da0-cf60399bbc44 | locations | The Drowned Throne | UNKNOWN | `51cb1c9c1d53679a5cf5f54e996adac011012358b196d587fea03298ea3af1b9` |
| notion:page:3b3e8214-84b0-817e-b670-fb3f9b2c3511 | locations | The Black Sluice | UNKNOWN | `039a79ce922001bda5d8955de543b556d6fdc71dc8294a2cbaed51a7ac7c3b19` |
| notion:page:3c2e8214-84b0-8125-9c06-df879a350b7e | locations | Shade Remnant Anauroch Bases | UNKNOWN | `a47754d88519dcd9db9361a9ac53bdc9a47ea6163d098a6471c305f7529d7ab6` |
| notion:page:3c2e8214-84b0-816a-8570-e8c7f1243e3b | locations | Caledor Sub-Territories | UNKNOWN | `cf57f68173a1b924f638bf3127d7850ca724720bea77cc668e0bcccc832bc081` |
| notion:page:3c2e8214-84b0-81b7-aabc-c22f10569330 | locations | Zhentarim Holdings (Moonsea & Dalelands) | UNKNOWN | `ed704f4ab4634acfea2bc4febbf8badbc4bcbadd9cb2e267cf00056c5062e999` |
| notion:page:3c2e8214-84b0-81ec-8167-fd325ff1717b | locations | Eastern Bulwark (Iron Sovereignty) | UNKNOWN | `53d8a1d0b4f1ad402ec9ea0d5db022bffd400625fa213d83869443b4198f0061` |
| notion:page:3c3e8214-84b0-815e-bb1a-c5e598d3d634 | locations | Warborn Engineering Campus — North River Site | UNKNOWN | `27bdb647841f26ff8ef08baa483ddcffc0b54ff248bb58cc9caffb5a47c964da` |
| notion:page:3cee8214-84b0-815b-ac54-e46e900f6d55 | locations | The Tally Room — Dalelands War-Accounting Facility | UNKNOWN | `a6460afc7e65103a1d9dfbf41167cd15fd26c7fca93860bf083c883ce375c1d3` |
| notion:page:3d1e8214-84b0-814e-aee1-db8532d9b16f | locations | The Sallow Pit (Field Ward, Waterdeep) | UNKNOWN | `8cca62fa728507a37cdc354ecc786720cc7e63ae911c10cda5b68119bdadd2dd` |
| notion:page:3d1e8214-84b0-8150-a65c-c6032705f27d | locations | Dock Ward Boathouse Altar (Umberlant) | UNKNOWN | `159cc16ad45915733de413141e18c70b242abd008350c55df3729905d193a2ac` |
| notion:page:3d1e8214-84b0-81d1-8583-d99753254127 | locations | The Brine Kettle (Cod Lane, Dock Ward) | UNKNOWN | `fd9ab35a0a8dc7c6417b70d46f2a9ae8533f3dc197ce3c22d1cb5b791bf04822` |
