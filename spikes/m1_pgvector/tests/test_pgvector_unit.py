import unittest

from spikes.m1_pgvector.utils import EMBEDDING_DIMENSION, vector_literal


class PgVectorUnitTests(unittest.TestCase):
    def test_vector_literal_uses_pgvector_input_format(self):
        values = [0.0] * EMBEDDING_DIMENSION
        values[0] = 1.25
        literal = vector_literal(values)
        self.assertTrue(literal.startswith("[1.25,0,0"))
        self.assertTrue(literal.endswith("]"))

    def test_vector_literal_rejects_wrong_dimension(self):
        with self.assertRaisesRegex(ValueError, "expected 384 dimensions"):
            vector_literal([0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
