from app.lcel_chain import build_chain


def test_chain_answers_a_single_question(fake_llm):
    chain = build_chain(fake_llm)
    out = chain.invoke("What is the rate limit on the Pro tier?")
    assert "600 requests per minute" in out


def test_chain_is_stateless_second_call_sees_nothing_of_the_first(fake_llm):
    chain = build_chain(fake_llm)
    chain.invoke("What is the rate limit on the Pro tier?")
    out = chain.invoke("Repeat the number from your first answer.")
    assert out == "I don't know."
    # the second prompt held only system + this call's human message
    assert len(fake_llm.calls[1]) == 2
