"""
Non-regression tests ensuring cryptographic randomness separation between modules.

poker/cards.py MUST use secrets.randbelow for actual card dealing (gameplay fairness).
poker/odds.py MUST NOT use secrets (performance optimization for Monte Carlo simulations).

Validates: Requirements 5.3
"""

import ast
import inspect
import textwrap

import poker.cards
import poker.odds


class TestCardsUsesCryptographicRandomness:
    """Verify poker/cards.py imports and uses secrets.randbelow."""

    def test_cards_imports_secrets(self):
        """poker/cards.py must import the secrets module."""
        source = inspect.getsource(poker.cards)
        tree = ast.parse(source)

        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.append(node.module)

        assert "secrets" in import_names, (
            "poker/cards.py must import 'secrets' for cryptographic card dealing"
        )

    def test_cards_uses_secrets_randbelow(self):
        """poker/cards.py must call secrets.randbelow for secure shuffling."""
        source = inspect.getsource(poker.cards)
        tree = ast.parse(source)

        uses_randbelow = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "secrets"
                    and node.attr == "randbelow"
                ):
                    uses_randbelow = True
                    break

        assert uses_randbelow, (
            "poker/cards.py must use secrets.randbelow for cryptographic card shuffling"
        )

    def test_cards_secure_shuffle_function_exists(self):
        """poker/cards.py must have a secure_shuffle function using secrets."""
        assert hasattr(poker.cards, "secure_shuffle"), (
            "poker/cards.py must define secure_shuffle()"
        )
        source = inspect.getsource(poker.cards.secure_shuffle)
        assert "secrets.randbelow" in source, (
            "secure_shuffle() must use secrets.randbelow"
        )


class TestOddsDoesNotUseCryptographicRandomness:
    """Verify poker/odds.py does NOT import or use secrets."""

    def test_odds_does_not_import_secrets(self):
        """poker/odds.py must not import the secrets module."""
        source = inspect.getsource(poker.odds)
        tree = ast.parse(source)

        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_names.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.append(node.module)

        assert "secrets" not in import_names, (
            "poker/odds.py must NOT import 'secrets' — it should use random.shuffle "
            "for Monte Carlo simulations"
        )

    def test_odds_does_not_reference_secrets(self):
        """poker/odds.py source must not contain any reference to secrets module."""
        source = inspect.getsource(poker.odds)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "secrets":
                raise AssertionError(
                    "poker/odds.py must not reference 'secrets' anywhere in its code"
                )
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "secrets":
                    raise AssertionError(
                        "poker/odds.py must not use secrets.randbelow or any secrets attribute"
                    )

    def test_odds_uses_random_shuffle(self):
        """poker/odds.py must use random.shuffle for Monte Carlo simulations."""
        source = inspect.getsource(poker.odds)
        tree = ast.parse(source)

        uses_random_shuffle = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "random"
                    and node.attr == "shuffle"
                ):
                    uses_random_shuffle = True
                    break

        assert uses_random_shuffle, (
            "poker/odds.py must use random.shuffle for Monte Carlo simulations"
        )
