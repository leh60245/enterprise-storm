import concurrent.futures
import dspy
import functools
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Dict, List, Optional, Union, TYPE_CHECKING

from .utils import ArticleTextProcessing

logging.basicConfig(
    level=logging.INFO, format="%(name)s : %(levelname)-8s : %(message)s"
)
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .logging_wrapper import LoggingWrapper


class InformationTable(ABC):
    """
    The InformationTable class serves as data class to store the information
    collected during KnowledgeCuration stage.

    Create subclass to incorporate more information as needed. For example,
    in STORM paper https://arxiv.org/pdf/2402.14207.pdf, additional information
    would be perspective guided dialogue history.
    """

    def __init__(self):
        pass

    @abstractmethod
    def retrieve_information(**kwargs):
        pass


class Information:
    """Class to represent detailed information.

    Inherits from Information to include a unique identifier (URL), and extends
    it with a description, snippets, and title of the storm information.

    Attributes:
        description (str): Brief description.
        snippets (list): List of brief excerpts or snippets.
        title (str): The title or headline of the information.
        url (str): The unique URL (serving as UUID) of the information.
    """

    def __init__(self, url, description, snippets, title, meta=None):
        """Initialize the Information object with detailed attributes.

        Args:
            url (str): The unique URL serving as the identifier for the information.
            description (str): Detailed description.
            snippets (list): List of brief excerpts or snippet.
            title (str): The title or headline of the information.
        """
        self.description = description
        self.snippets = snippets
        self.title = title
        self.url = url
        self.meta = meta if meta is not None else {}
        self.citation_uuid = -1

    def __hash__(self):
        return hash(
            (
                self.url,
                tuple(sorted(self.snippets)),
            )
        )

    def __eq__(self, other):
        if not isinstance(other, Information):
            return False
        return (
            self.url == other.url
            and set(self.snippets) == set(other.snippets)
            and self._meta_str() == other._meta_str()
        )

    def __hash__(self):
        return int(
            self._md5_hash((self.url, tuple(sorted(self.snippets)), self._meta_str())),
            16,
        )

    def _meta_str(self):
        """Generate a string representation of relevant meta information."""
        return f"Question: {self.meta.get('question', '')}, Query: {self.meta.get('query', '')}"

    def _md5_hash(self, value):
        """Generate an MD5 hash for a given value."""
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, sort_keys=True)
        return hashlib.md5(str(value).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, info_dict):
        """Create a Information object from a dictionary.
           Usage: info = Information.from_dict(storm_info_dict)

        Args:
            info_dict (dict): A dictionary containing keys 'url', 'description',
                              'snippets', and 'title' corresponding to the object's attributes.

        Returns:
            Information: An instance of Information.
        """
        info = cls(
            url=info_dict["url"],
            description=info_dict["description"],
            snippets=info_dict["snippets"],
            title=info_dict["title"],
            meta=info_dict.get("meta", None),
        )
        info.citation_uuid = int(info_dict.get("citation_uuid", -1))
        return info

    def to_dict(self):
        return {
            "url": self.url,
            "description": self.description,
            "snippets": self.snippets,
            "title": self.title,
            "meta": self.meta,
            "citation_uuid": self.citation_uuid,
        }


class ArticleSectionNode:
    """
    The ArticleSectionNode is the dataclass for handling the section of the article.
    The content storage, section writing preferences are defined in this node.
    """

    def __init__(self, section_name: str, content=None):
        """
        section_name: section heading in string format. E.g. Introduction, History, etc.
        content: content of the section. Up to you for design choice of the data structure.
        """
        self.section_name = section_name
        self.content = content
        self.children = []
        self.preference = None

    def add_child(self, new_child_node, insert_to_front=False):
        if insert_to_front:
            self.children.insert(0, new_child_node)
        else:
            self.children.append(new_child_node)

    def remove_child(self, child):
        self.children.remove(child)


class Article(ABC):
    def __init__(self, topic_name):
        self.root = ArticleSectionNode(topic_name)

    def find_section(
        self, node: ArticleSectionNode, name: str
    ) -> Optional[ArticleSectionNode]:
        """
        Return the node of the section given the section name.

        Args:
            node: the node as the root to find.
            name: the name of node as section name

        Return:
            reference of the node or None if section name has no match
        """
        if node.section_name == name:
            return node
        for child in node.children:
            result = self.find_section(child, name)
            if result:
                return result
        return None

    @abstractmethod
    def to_string(self) -> str:
        """
        Export Article object into string representation.
        """

    def get_outline_tree(self):
        """
        Generates a hierarchical tree structure representing the outline of the document.

        Returns:
            Dict[str, Dict]: A nested dictionary representing the hierarchical structure of the document's outline.
                             Each key is a section name, and the value is another dictionary representing the child sections,
                             recursively forming the tree structure of the document's outline. If a section has no subsections,
                             its value is an empty dictionary.

        Example:
            Assuming a document with a structure like:
            - Introduction
                - Background
                - Objective
            - Methods
                - Data Collection
                - Analysis
            The method would return:
            {
                'Introduction': {
                    'Background': {},
                    'Objective': {}
                },
                'Methods': {
                    'Data Collection': {},
                    'Analysis': {}
                }
            }
        """

        def build_tree(node) -> Dict[str, Dict]:
            tree = {}
            for child in node.children:
                tree[child.section_name] = build_tree(child)
            return tree if tree else {}

        return build_tree(self.root)

    def get_first_level_section_names(self) -> List[str]:
        """
        Get first level section names
        """
        return [i.section_name for i in self.root.children]

    @classmethod
    @abstractmethod
    def from_string(cls, topic_name: str, article_text: str):
        """
        Create an instance of the Article object from a string
        """
        pass

    def prune_empty_nodes(self, node=None):
        if node is None:
            node = self.root

        node.children[:] = [
            child for child in node.children if self.prune_empty_nodes(child)
        ]

        if (node.content is None or node.content == "") and not node.children:
            return None
        else:
            return node


class Retriever:
    """
    An abstract base class for retriever modules. It provides a template for retrieving information based on a query.

    This class should be extended to implement specific retrieval functionalities.
    Users can design their retriever modules as needed by implementing the retrieve method.
    The retrieval model/search engine used for each part should be declared with a suffix '_rm' in the attribute name.

    Post-Retrieval Processing:
    - Section-Based Boosting: 질문에 "개요", "소개" 등이 포함되면 해당 섹션 청크에 가산점 부여
    - Diversity Enforcement: Text/Table 비율 강제 (Table 편향 방지)
    """

    # 섹션 가중치 부여를 위한 키워드 매핑
    SECTION_BOOST_KEYWORDS = {
        "overview": ["개요", "overview", "소개", "introduction", "회사의 개요", "기업 개요"],
        "business": ["사업", "business", "사업 내용", "사업의 내용", "주요 사업"],
        "financial": ["재무", "financial", "재무제표", "매출", "손익"],
        "history": ["연혁", "history", "설립", "역사"],
    }

    # 섹션 부스트 점수
    SECTION_BOOST_SCORE = 0.3

    # 다양성 강제: 최소 Text 비율 (0.4 = 40% 이상은 Text여야 함)
    MIN_TEXT_RATIO = 0.4

    def __init__(self, rm: dspy.Retrieve, max_thread: int = 1):
        self.max_thread = max_thread
        self.rm = rm

    def collect_and_reset_rm_usage(self):
        combined_usage = []
        if hasattr(getattr(self, "rm"), "get_usage_and_reset"):
            combined_usage.append(getattr(self, "rm").get_usage_and_reset())

        name_to_usage = {}
        for usage in combined_usage:
            for model_name, query_cnt in usage.items():
                if model_name not in name_to_usage:
                    name_to_usage[model_name] = query_cnt
                else:
                    name_to_usage[model_name] += query_cnt

        return name_to_usage

    def _detect_query_intent(self, query: str) -> List[str]:
        """
        질문에서 섹션 의도(intent)를 감지

        Args:
            query: 검색 쿼리

        Returns:
            감지된 섹션 카테고리 리스트 (예: ["overview", "business"])
        """
        detected_intents = []
        query_lower = query.lower()

        for category, keywords in self.SECTION_BOOST_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    detected_intents.append(category)
                    break

        return detected_intents

    def _calculate_section_boost(self, title: str, intents: List[str]) -> float:
        """
        섹션 제목과 질문 의도를 비교하여 부스트 점수 계산

        Args:
            title: 청크의 섹션 제목 (section_path)
            intents: 감지된 질문 의도

        Returns:
            부스트 점수 (0.0 ~ SECTION_BOOST_SCORE)
        """
        if not intents or not title:
            return 0.0

        title_lower = title.lower()

        for intent in intents:
            keywords = self.SECTION_BOOST_KEYWORDS.get(intent, [])
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    logger.debug(f"Section boost applied: '{title}' matches intent '{intent}'")
                    return self.SECTION_BOOST_SCORE

        return 0.0

    def _get_chunk_type(self, data: dict) -> str:
        """
        검색 결과에서 chunk_type 추출

        Args:
            data: 검색 결과 딕셔너리

        Returns:
            "text" 또는 "table"
        """
        # URL에서 chunk_type 힌트 추출 (dart_report_X_chunk_Y 형식)
        url = data.get("url", "")
        content = data.get("content", "") or (data.get("snippets", [""])[0] if data.get("snippets") else "")

        # 테이블 감지 휴리스틱:
        # 1. content에 마크다운 테이블 구분자(|) 포함
        # 2. content에 "[표 데이터]" 태그 포함
        # 3. title에 "표" 포함
        if "|" in content and content.count("|") > 5:
            return "table"
        if "[표 데이터]" in content:
            return "table"
        if "표" in data.get("title", ""):
            return "table"

        return "text"

    def _apply_diversity_enforcement(
        self, results: List[dict], top_k: int = None
    ) -> List[dict]:
        """
        Diversity Enforcement: Text/Table 비율 강제

        AI가 테이블만 편식하지 못하게, 최소 Text 비율을 강제합니다.

        Args:
            results: 검색 결과 리스트 (score로 정렬됨)
            top_k: 최종 선택할 개수 (None이면 전체 반환)

        Returns:
            다양성이 보장된 결과 리스트
        """
        if not results:
            return results

        if top_k is None:
            top_k = len(results)

        # chunk_type 분류
        text_results = []
        table_results = []

        for r in results:
            chunk_type = self._get_chunk_type(r)
            if chunk_type == "text":
                text_results.append(r)
            else:
                table_results.append(r)

        # 최소 Text 개수 계산
        min_text_count = max(1, int(top_k * self.MIN_TEXT_RATIO))

        # 결과 구성
        final_results = []

        # 1. Text에서 min_text_count 만큼 먼저 선택
        for r in text_results[:min_text_count]:
            final_results.append(r)

        # 2. 나머지 슬롯은 score 순으로 채움 (Text/Table 무관)
        remaining_slot = top_k - len(final_results)
        remaining_pool = [r for r in results if r not in final_results]

        for r in remaining_pool[:remaining_slot]:
            final_results.append(r)

        logger.info(
            f"Diversity Enforcement: {len(text_results)} text, {len(table_results)} table "
            f"→ Selected {len([r for r in final_results if self._get_chunk_type(r) == 'text'])} text, "
            f"{len([r for r in final_results if self._get_chunk_type(r) == 'table'])} table"
        )

        return final_results

    def retrieve(
        self, query: Union[str, List[str]], exclude_urls: List[str] = []
    ) -> List[Information]:
        queries = query if isinstance(query, list) else [query]
        to_return = []

        # 질문 의도 감지 (전체 쿼리에서)
        combined_query = " ".join(queries)
        detected_intents = self._detect_query_intent(combined_query)
        if detected_intents:
            logger.info(f"Detected query intents: {detected_intents}")

        def process_query(q):
            retrieved_data_list = self.rm(
                query_or_queries=[q], exclude_urls=exclude_urls
            )
            local_to_return = []
            for data in retrieved_data_list:
                # data가 dspy.Prediction 객체인 경우 딕셔너리로 변환
                if hasattr(data, '_store') and not isinstance(data, dict):
                    # dspy.Prediction의 내부 저장소 사용
                    data = dict(data._store)
                elif hasattr(data, '__dict__') and not isinstance(data, dict):
                    data = {k: v for k, v in data.__dict__.items() if not k.startswith('_')}

                # snippets 필드가 없으면 content에서 생성
                if "snippets" not in data:
                    content = data.get("content", "")
                    data["snippets"] = [content] if content else []

                for i in range(len(data["snippets"])):
                    # STORM generate the article with citations. We do not consider multi-hop citations.
                    # Remove citations in the source to avoid confusion.
                    data["snippets"][i] = ArticleTextProcessing.remove_citations(
                        data["snippets"][i]
                    )

                # Section-Based Boosting: score 조정
                original_score = data.get("score", 0.0)
                section_boost = self._calculate_section_boost(
                    data.get("title", ""), detected_intents
                )
                adjusted_score = original_score + section_boost

                if section_boost > 0:
                    logger.debug(
                        f"Boosted '{data.get('title', '')[:30]}...' "
                        f"score: {original_score:.3f} → {adjusted_score:.3f}"
                    )

                # score 업데이트
                data["score"] = adjusted_score

                local_to_return.append(data)
            return local_to_return

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_thread
        ) as executor:
            results = list(executor.map(process_query, queries))

        # 모든 결과 합치기
        all_results = []
        for result in results:
            all_results.extend(result)

        # Score 기준 재정렬
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Diversity Enforcement 적용
        all_results = self._apply_diversity_enforcement(all_results)

        # Information 객체로 변환
        for data in all_results:
            storm_info = Information.from_dict(data)
            storm_info.meta["query"] = combined_query
            to_return.append(storm_info)

        return to_return


class KnowledgeCurationModule(ABC):
    """
    The interface for knowledge curation stage. Given topic, return collected information.
    """

    def __init__(self, retriever: Retriever):
        """
        Store args and finish initialization.
        """
        self.retriever = retriever

    @abstractmethod
    def research(self, topic) -> InformationTable:
        """
        Curate information and knowledge for the given topic

        Args:
            topic: topic of interest in natural language.

        Returns:
            collected_information: collected information in InformationTable type.
        """
        pass


class OutlineGenerationModule(ABC):
    """
    The interface for outline generation stage. Given topic, collected information from knowledge
    curation stage, generate outline for the article.
    """

    @abstractmethod
    def generate_outline(
        self, topic: str, information_table: InformationTable, **kwargs
    ) -> Article:
        """
        Generate outline for the article. Required arguments include:
            topic: the topic of interest
            information_table: knowledge curation data generated from KnowledgeCurationModule

        More arguments could be
            1. draft outline
            2. user provided outline

        Returns:
            article_outline of type ArticleOutline
        """
        pass


class ArticleGenerationModule(ABC):
    """
    The interface for article generation stage. Given topic, collected information from
    knowledge curation stage, generated outline from outline generation stage,
    """

    @abstractmethod
    def generate_article(
        self,
        topic: str,
        information_table: InformationTable,
        article_with_outline: Article,
        **kwargs,
    ) -> Article:
        """
        Generate article. Required arguments include:
            topic: the topic of interest
            information_table: knowledge curation data generated from KnowledgeCurationModule
            article_with_outline: article with specified outline from OutlineGenerationModule
        """
        pass


class ArticlePolishingModule(ABC):
    """
    The interface for article generation stage. Given topic, collected information from
    knowledge curation stage, generated outline from outline generation stage,
    """

    @abstractmethod
    def polish_article(self, topic: str, draft_article: Article, **kwargs) -> Article:
        """
        Polish article. Required arguments include:
            topic: the topic of interest
            draft_article: draft article from ArticleGenerationModule.
        """
        pass


def log_execution_time(func):
    """Decorator to log the execution time of a function."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        result = func(self, *args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        logger.info(f"{func.__name__} executed in {execution_time:.4f} seconds")
        self.time[func.__name__] = execution_time
        return result

    return wrapper


class LMConfigs(ABC):
    """Abstract base class for language model configurations of the knowledge curation engine.

    The language model used for each part should be declared with a suffix '_lm' in the attribute name.
    """

    def __init__(self):
        pass

    def init_check(self):
        for attr_name in self.__dict__:
            if "_lm" in attr_name and getattr(self, attr_name) is None:
                logging.warning(
                    f"Language model for {attr_name} is not initialized. Please call set_{attr_name}()"
                )

    def collect_and_reset_lm_history(self):
        history = []
        for attr_name in self.__dict__:
            if "_lm" in attr_name and hasattr(getattr(self, attr_name), "history"):
                history.extend(getattr(self, attr_name).history)
                getattr(self, attr_name).history = []

        return history

    def collect_and_reset_lm_usage(self):
        combined_usage = []
        for attr_name in self.__dict__:
            if "_lm" in attr_name and hasattr(
                getattr(self, attr_name), "get_usage_and_reset"
            ):
                combined_usage.append(getattr(self, attr_name).get_usage_and_reset())

        model_name_to_usage = {}
        for usage in combined_usage:
            for model_name, tokens in usage.items():
                if model_name not in model_name_to_usage:
                    model_name_to_usage[model_name] = tokens
                else:
                    model_name_to_usage[model_name]["prompt_tokens"] += tokens[
                        "prompt_tokens"
                    ]
                    model_name_to_usage[model_name]["completion_tokens"] += tokens[
                        "completion_tokens"
                    ]

        return model_name_to_usage

    def log(self):
        return OrderedDict(
            {
                attr_name: getattr(self, attr_name).kwargs
                for attr_name in self.__dict__
                if "_lm" in attr_name and hasattr(getattr(self, attr_name), "kwargs")
            }
        )


class Engine(ABC):
    def __init__(self, lm_configs: LMConfigs):
        self.lm_configs = lm_configs
        self.time = {}
        self.lm_cost = {}  # Cost of language models measured by in/out tokens.
        self.rm_cost = {}  # Cost of retrievers measured by number of queries.

    def log_execution_time_and_lm_rm_usage(self, func):
        """Decorator to log the execution time, language model usage, and retrieval model usage of a function."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time
            self.time[func.__name__] = execution_time
            logger.info(f"{func.__name__} executed in {execution_time:.4f} seconds")
            self.lm_cost[func.__name__] = self.lm_configs.collect_and_reset_lm_usage()
            if hasattr(self, "retriever"):
                self.rm_cost[func.__name__] = (
                    self.retriever.collect_and_reset_rm_usage()
                )
            return result

        return wrapper

    def apply_decorators(self):
        """Apply decorators to methods that need them."""
        methods_to_decorate = [
            method_name
            for method_name in dir(self)
            if callable(getattr(self, method_name)) and method_name.startswith("run_")
        ]
        for method_name in methods_to_decorate:
            original_method = getattr(self, method_name)
            decorated_method = self.log_execution_time_and_lm_rm_usage(original_method)
            setattr(self, method_name, decorated_method)

    @abstractmethod
    def run_knowledge_curation_module(self, **kwargs) -> Optional[InformationTable]:
        pass

    @abstractmethod
    def run_outline_generation_module(self, **kwarg) -> Article:
        pass

    @abstractmethod
    def run_article_generation_module(self, **kwarg) -> Article:
        pass

    @abstractmethod
    def run_article_polishing_module(self, **kwarg) -> Article:
        pass

    @abstractmethod
    def run(self, **kwargs):
        pass

    def summary(self):
        print("***** Execution time *****")
        for k, v in self.time.items():
            print(f"{k}: {v:.4f} seconds")

        print("***** Token usage of language models: *****")
        for k, v in self.lm_cost.items():
            print(f"{k}")
            for model_name, tokens in v.items():
                print(f"    {model_name}: {tokens}")

        print("***** Number of queries of retrieval models: *****")
        for k, v in self.rm_cost.items():
            print(f"{k}: {v}")

    def reset(self):
        self.time = {}
        self.lm_cost = {}
        self.rm_cost = {}


class Agent(ABC):
    """
    Interface for STORM and Co-STORM LLM agent

    This class must be implemented by any subclass of `Agent` to define how the agent generates an utterance.
    The generated utterance can be influenced by the conversation history, knowledge base, and any additional parameters passed via `kwargs`.
    The implementation should align with the specific role and perspective of the agent, as defined by the agent's topic, role name, and role description.

    Args:
        knowledge_base (KnowledgeBase): The current knowledge base (e.g., mind map in Co-STORM) that contains the accumulated information relevant to the conversation.
        conversation_history (List[ConversationTurn]): A list of past conversation turns, providing context for generating the next utterance.
                                                       The agent can refer to this history to maintain continuity and relevance in the conversation.
        logging_wrapper (LoggingWrapper): A wrapper used for logging important events during the utterance generation process.
        **kwargs: Additional arguments that can be passed to the method for more specialized utterance generation behavior depending on the agent's specific implementation.

    Returns:
        ConversationTurn: A new conversation turn generated by the agent, containing the agent's response, including the role, utterance type, and relevant information from the knowledge base.

    Notes:
        - Subclasses of `Agent` should define the exact strategy for generating the utterance, which could involve interacting with a language model, retrieving relevant knowledge, or following specific conversational policies.
        - The agent's role, perspective, and the knowledge base content will influence how the utterance is formulated.
    """

    from .dataclass import KnowledgeBase, ConversationTurn

    def __init__(self, topic: str, role_name: str, role_description: str):
        self.topic = topic
        self.role_name = role_name
        self.role_description = role_description

    def get_role_description(self):
        if self.role_description:
            return f"{self.role_name}: {self.role_description}"
        return self.role_name

    @abstractmethod
    def generate_utterance(
        self,
        knowledge_base: KnowledgeBase,
        conversation_history: List[ConversationTurn],
        logging_wrapper: "LoggingWrapper",
        **kwargs,
    ):
        pass
