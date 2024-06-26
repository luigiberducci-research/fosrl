from fosco.common.consts import VerifierType, TimeDomain, CertificateType
from fosco.translator.translator import Translator
from fosco.translator.translator_cbf import MLPTranslator
from fosco.translator.translator_cbf_dt import MLPTranslatorDT
from fosco.translator.translator_rcbf import RobustMLPTranslator
from fosco.translator.translator_rcbf_dt import RobustMLPTranslatorDT


def make_translator(
    certificate_type: str | CertificateType,
    verifier_type: str | VerifierType,
    time_domain: str | TimeDomain,
    **kwargs,
) -> Translator:
    """
    Factory function for translators.
    """
    if isinstance(certificate_type, str):
        certificate_type = CertificateType[certificate_type.upper()]
    if isinstance(verifier_type, str):
        verifier_type = VerifierType[verifier_type.upper()]
    if isinstance(time_domain, str):
        time_domain = TimeDomain[time_domain.upper()]

    if time_domain == TimeDomain.CONTINUOUS and verifier_type in [
        VerifierType.Z3,
        VerifierType.DREAL,
    ]:
        if certificate_type == CertificateType.RCBF:
            return RobustMLPTranslator(**kwargs)
        elif certificate_type == CertificateType.CBF:
            return MLPTranslator(**kwargs)
        else:
            raise NotImplementedError(
                f"Translator for certificate={certificate_type}, time={time_domain}, verifier={verifier_type} not implemented"
            )
    elif time_domain == TimeDomain.DISCRETE and verifier_type in [
        VerifierType.Z3,
        VerifierType.DREAL,
    ]:
        if certificate_type == CertificateType.RCBF:
            return RobustMLPTranslatorDT(**kwargs)
        elif certificate_type == CertificateType.CBF:
            return MLPTranslatorDT(**kwargs)
        else:
            raise NotImplementedError(
                f"Translator for certificate={certificate_type}, time={time_domain}, verifier={verifier_type} not implemented"
            )
    else:
        raise NotImplementedError(
            f"Translator for certificate={certificate_type}, time={time_domain}, verifier={verifier_type} not implemented"
        )
