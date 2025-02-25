from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import (
    Any,
    ClassVar,
    Generic,
    NotRequired,
    Protocol,
    Required,
    Self,
    TypedDict,
    TypeVar,
)

from django.core.exceptions import ImproperlyConfigured

from .. import embeddings, tokens
from ..types import (
    AIResponse,
    TextSplitterLengthCalculatorProtocol,
    TextSplitterProtocol,
)


class BaseConfigSettingsDict(TypedDict):
    MODEL_ID: Required[str]
    TOKEN_LIMIT: NotRequired[int | None]
    CHUNK_OVERLAP_CHARACTERS: NotRequired[int | None]


class BaseChatConfigSettingsDict(BaseConfigSettingsDict):
    pass


class BaseEmbeddingConfigSettingsDict(BaseConfigSettingsDict):
    EMBEDDING_OUTPUT_DIMENSIONS: NotRequired[int | None]


ConfigSettings = TypeVar(
    "ConfigSettings", bound=BaseConfigSettingsDict, contravariant=True
)


ChatConfigSettings = TypeVar(
    "ChatConfigSettings", bound=BaseChatConfigSettingsDict, contravariant=True
)

EmbeddingConfigSettings = TypeVar(
    "EmbeddingConfigSettings", bound=BaseEmbeddingConfigSettingsDict, contravariant=True
)


class ConfigClassProtocol(Protocol[ConfigSettings]):
    @classmethod
    def from_settings(cls, config: ConfigSettings, **kwargs: Any) -> Self:
        ...


@dataclass(kw_only=True)
class BaseConfig(ConfigClassProtocol[ConfigSettings]):
    chunk_overlap_characters: int
    model_id: str
    text_splitter_class: type[TextSplitterProtocol]
    text_splitter_length_calculator_class: type[TextSplitterLengthCalculatorProtocol]
    token_limit: int

    @classmethod
    def from_settings(
        cls,
        config: ConfigSettings,
        *,
        text_splitter_class: type[TextSplitterProtocol],
        text_splitter_length_calculator_class: type[
            TextSplitterLengthCalculatorProtocol
        ],
        **kwargs: Any,
    ) -> Self:
        token_limit = cls.get_token_limit(
            model_id=config["MODEL_ID"], custom_value=config.get("TOKEN_LIMIT")
        )
        chunk_overlap_characters = cls.get_chunk_overlap(
            model_id=config["MODEL_ID"],
            custom_value=config.get("CHUNK_OVERLAP_CHARACTERS"),
        )

        return cls(
            chunk_overlap_characters=chunk_overlap_characters,
            model_id=config["MODEL_ID"],
            text_splitter_class=text_splitter_class,
            text_splitter_length_calculator_class=text_splitter_length_calculator_class,
            token_limit=token_limit,
            **kwargs,
        )

    @classmethod
    def get_token_limit(cls, *, model_id: str, custom_value: int | None) -> int:
        if custom_value is not None:
            try:
                return int(custom_value)
            except ValueError as e:
                raise ImproperlyConfigured(
                    f'"TOKEN_LIMIT" is not an "int", it is a "{type(custom_value)}".'
                ) from e
        try:
            return tokens.get_default_token_limit(model_id=model_id)
        except tokens.NoTokenLimitFound as e:
            raise ImproperlyConfigured(
                f'"TOKEN_LIMIT" is not configured for model "{model_id}".'
            ) from e

    @classmethod
    def get_chunk_overlap(cls, *, model_id: str, custom_value: int | None) -> int:
        if custom_value is not None:
            try:
                return int(custom_value)
            except ValueError as e:
                raise ImproperlyConfigured(
                    f'"CHUNK_OVERLAP_CHARACTERS" is not an "int", it is a "{type(custom_value)}".'
                ) from e
        return tokens.get_default_chunk_overlap()


@dataclass(kw_only=True)
class BaseChatConfig(BaseConfig[ChatConfigSettings]):
    pass


@dataclass(kw_only=True)
class BaseEmbeddingConfig(BaseConfig[EmbeddingConfigSettings]):
    embedding_output_dimensions: int

    @classmethod
    def from_settings(
        cls,
        config: EmbeddingConfigSettings,
        *,
        text_splitter_class: type[TextSplitterProtocol],
        text_splitter_length_calculator_class: type[
            TextSplitterLengthCalculatorProtocol
        ],
        **kwargs: Any,
    ) -> Self:
        embedding_output_dimensions = cls.get_embedding_output_dimensions(
            model_id=config["MODEL_ID"],
            custom_value=config.get("EMBEDDING_OUTPUT_DIMENSIONS"),
        )
        kwargs.setdefault("embedding_output_dimensions", embedding_output_dimensions)
        return super().from_settings(
            config=config,
            text_splitter_class=text_splitter_class,
            text_splitter_length_calculator_class=text_splitter_length_calculator_class,
            **kwargs,
        )

    @classmethod
    def get_embedding_output_dimensions(
        cls, *, model_id: str, custom_value: int | None
    ) -> int:
        if custom_value is not None:
            try:
                return int(custom_value)
            except ValueError as e:
                raise ImproperlyConfigured(
                    f'"EMBEDDING_OUTPUT_DIMENSIONS" is not an "int", it is a "{type(custom_value)}".'
                ) from e
        try:
            return embeddings.get_default_embedding_output_dimensions(model_id=model_id)
        except embeddings.EmbeddingOutputDimensionsNotFound as e:
            raise ImproperlyConfigured(
                f'"EMBEDDING_OUTPUT_DIMENSIONS" is not configured for model "{model_id}".'
            ) from e


AnyBackendConfig = TypeVar("AnyBackendConfig", bound=BaseConfig)
ChatBackendConfig = TypeVar("ChatBackendConfig", bound=BaseChatConfig)
EmbeddingBackendConfig = TypeVar("EmbeddingBackendConfig", bound=BaseEmbeddingConfig)


class BaseBackend(Generic[AnyBackendConfig]):
    config_cls: ClassVar[type[BaseConfig]]
    config: AnyBackendConfig

    def __init__(self, *, config: AnyBackendConfig) -> None:
        self.config = config

    def get_text_splitter(self) -> TextSplitterProtocol:
        return self.config.text_splitter_class(
            chunk_size=self.config.token_limit,
            chunk_overlap=self.config.chunk_overlap_characters,
            length_function=self.get_splitter_length_calculator().get_splitter_length,
        )

    def get_splitter_length_calculator(self) -> TextSplitterLengthCalculatorProtocol:
        return self.config.text_splitter_length_calculator_class()


class BaseChatBackend(BaseBackend[ChatBackendConfig]):
    config_cls: ClassVar[type[BaseChatConfig]]
    config: ChatBackendConfig

    def chat(self, *, user_messages: Sequence[str]) -> AIResponse:
        ...


class BaseEmbeddingBackend(BaseBackend[EmbeddingBackendConfig]):
    config_cls: ClassVar[type[BaseEmbeddingConfig]]
    config: EmbeddingBackendConfig

    def embed(self, inputs: Iterable[str]) -> Iterator[list[float]]:
        ...

    @property
    def embedding_output_dimensions(self) -> int:
        return self.config.embedding_output_dimensions
