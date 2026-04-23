import styles from "./GcuPage.module.css";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import {
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { Link } from "react-router-dom";

export default function GcuPage() {
  const { t } = useTranslation();
  const [trigger, { isLoading }] = useValidateGcuControlPlaneV1GcuPostMutation();
  const { data: userDetails, refetch } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const { gcuVersion } = useFrontendProperties();

  const [hasReachedBottom, setHasReachedBottom] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasReachedBottom(true);
          observer.unobserve(entry.target);
        } else {
          setHasReachedBottom(false);
        }
      },
      {
        root: null,
        threshold: 1.0,
      },
    );

    if (bottomRef.current) {
      observer.observe(bottomRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleAcceptGcu = async () => {
    await trigger().unwrap();
    refetch();
  };

  return (
    <div className={styles.gcuContainer}>
      <div className={styles.gcuTitle}>{t("rework.gcu.title")}</div>
      <div className={styles.gcuContent}>
        <div className={styles.gcuSection}>Last update: April 2026</div>
        <div className={styles.gcuSection}>
          <h2>Introduction</h2>
          <div>
            Thales Services Numériques (“Thales”) has developed a secure generative agentic AI tool called Prism
            (“PRISM”) and makes it available to Thales’ internal active employees and interns (“Users”).
          </div>
          <div>
            While the use of PRISM may bring substantial advantages to Thales, its use may also pose some risks, notably
            concerning the protection of Thales information and data if Users do not carefully follow usage limitations
            set herein. The use of PRISM by Users is governed by these terms of use (the “Terms of Use”) which include
            this document and any other documentation, guideline or policy referred to herein. The access to PRISM is
            subject to the Users having accessed, read and accepted these Terms of Use electronically. Users may have
            access at any time to the Terms of Use via this link:
            <a href={`${window.location.origin}/gcu`}>{`${window.location.origin}/gcu`}</a> The Users acknowledge that
            refusal of these Terms of Use will block their access to and use of PRISM.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>PRISM Description</h2>
          <div>
            PRISM is based on large language models (LLM) Mistral Medium from Mistral and allows for the use of an AI
            agent that complies with Thales privacy and security constraints. PRISM’s use is made available to Users as
            follows:
          </div>
          <div>
            The Platform provides users with generative AI tools and data management capabilities. The following terms
            govern the creation and management of AI agents (hereafter referred to as "Lumis") and their associated
            knowledge bases.
          </div>
          <h3>1. General Usage of Lumis and RAG</h3>
          <div>
            Agent Creation: Users may create Lumis to assist in their professional activities. These agents leverage
            Retrieval-Augmented Generation (RAG) technology to process uploaded documentation.
          </div>
          <div>
            Knowledge Bases: Users may ingest files into dedicated knowledge bases to provide Lumis with specific
            business context, enabling tailored guidance, analysis, and support.
          </div>
          <h3>2. Private Workspace (Individual Use)</h3>
          <div>
            Personal Environment: Every user is provided with a private workspace to create Lumis and manage personal
            knowledge bases.
          </div>
          <div>
            Confidentiality: Assets within the Private Workspace are strictly restricted to the individual user and are
            not accessible by other users or teams unless explicitly shared or moved by the user.
          </div>
          <h3>3. Collaborative Workspaces (Team Use)</h3>
          <div>
            Users may request the creation of a "Team" to collaborate on shared Lumis and collective knowledge bases.
            Within a Team, access and management rights are defined by the following roles:
          </div>
          <div>
            Owner: The primary administrator responsible for managing team settings and member access
            (invitations/removals).
          </div>
          <div>
            Editor: Users authorized to create, configure, and manage both the Team's Lumis and its shared knowledge
            bases. Owners inherently hold Editor rights.
          </div>
          <div>
            Member: Users restricted to interacting with and utilizing the Lumis developed by Owners and Editors.
            Members do not have the authority to manage the Team's RAG or modify agent configurations.
          </div>
          <h3>Team Creation and Validation Process</h3>
          <div>
            Request and Authorization: The creation of a Team is not automatic. Users wishing to establish a
            collaborative workspace must contact the Platform's Operations Team (Run Team) to obtain the necessary
            permissions.
          </div>
          <div>
            Mandatory Risk Assessment: Each request is subject to a formal validation process. This procedure is
            designed to assess and mitigate risks related to the criticality of the intended use cases and the
            sensitivity of the data to be ingested. The Platform reserves the right to deny Team creation if the use
            case or data sensitivity does not comply with the Group’s security standards and risk management policies.
          </div>
          <h3>4. Liability and Responsibility</h3>
          <div>
            Content Responsibility: Owners and Editors are jointly and severally responsible for the specific use cases,
            the accuracy of the data ingested into the RAG, and the resulting outputs or behaviors of the Lumis created
            within their Team.
          </div>
          <div>
            Compliance: Users must ensure that any documentation uploaded to the Platform complies with internal
            security policies and intellectual property rights.
          </div>
          <h3>5. Access Fees</h3>
          <div>
            Service Cost: Access to the PRISM platform is currently provided free of charge for both individual users
            and collaborative communities. The Group reserves the right to review this policy in accordance with future
            infrastructure or licensing requirements.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Eligibility and Access to PRISM</h2>
          <div>
            Access to and use of PRISM is only allowed for Users who have read and accepted the Terms of Use. Thales
            reserves the right to unilaterally determine if a User is eligible to use PRISM. Pursuant to Digital
            Resources Acceptable Use Charter, each User shall use its Thales account credentials (Thales email address
            and password) to access PRISM. Users shall always log in to access PRISM through SSO.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Personal Data Protection</h2>
          <div>
            Personal Data related to User’s use of PRISM will be processed in accordance with the applicable regulation
            and the Thales Personal Data Protection Policies. Your prompts and completions are stored to support the
            conversation history and may be audited for security and compliance purposes. For more details, please
            consult the privacy notice.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Input</h2>
          <div>
            “Input” refers to data ingested by Users in PRISM, based on which PRISM produces an Output. In no event,
            Users shall ingest or infer Thales information classified beyond C3 (Thales Group Confidential) as Input
            when using PRISM, in accordance with the Instruction for Protection of Group Information. Each User is
            responsible for always verifying that Thales has the right to use adequately the information used as Input.
            In particular, each User shall verify that an Input is not protected by any third party’s license or rights
            before ingesting it in PRISM and refer to Thales’ department for intellectual property rights clearance in
            case of doubts.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Output</h2>
          <div>
            “Output” shall refer to the results produced by PRISM, based on the textual prompts (text-to-text, or
            text-to-image. An Output could be (but not limited to) a textual response to a User’s question, a
            recommendation, a roadmap guidance, an image, a graphic or a design. Thales shall remain the owner of all
            Output content and thus all rules and requirements applicable to Thales information under Instruction for
            Protection of Group Information. Users shall:
          </div>
          <div>
            · always conduct a human oversight verification on the accuracy, comprehensiveness and reliability of the
            Output before using it;
          </div>
          <div>· always keep evidence of the Input to be able to explain the Output generated;</div>
          <div>
            · refer to Thales’ department for intellectual property rights clearance when Outputs are shared outside of
            Thales;
          </div>
          <div>· when shared with others, expressly disclose that the Output was artificially generated.</div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Authorized Use Context</h2>
          <div>Users shall use PRISM only in the following contexts:</div>
          <div>
            · Professional and Business Purposes: Any use case intended to enhance professional productivity, analyze
            business documentation, or support internal decision-making processes, provided such use remains within the
            scope of the user’s professional duties.
          </div>
          <div>
            · Regulatory Compliance: Users are strictly required to ensure that their use cases—and the subsequent
            deployment of Lumis—comply with the EU AI Act and the General Data Protection Regulation (GDPR).
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Limitations and Restrictions of Use</h2>
          <h3>1. Users shall not</h3>
          <div>
            · Use PRISM for personal purposes or for purposes other than Thales internal business or administrative
            needs;
          </div>
          <div>
            · Process content or generate content through PRISM that can inflict harm on individuals or society,
            including but not limited to child sexual exploitation and abuse, grooming, non-consensual intimate content,
            sexual solicitation, trafficking, any sexually graphic, including consensual pornographic content and
            intimate descriptions of sexual acts, suicide and self-injury, terrorism, violent threats, hate speech and
            discrimination, bullying and harassment, active malware or exploits;
          </div>
          <div>· Violate Thales Digital Resources Acceptable Use Charter, Thales Digital Ethic Charter;</div>
          <div>
            · Use the Service in any way that is prohibited by law, regulation, government order, or decree, or any use
            that violates the rights of others;
          </div>
          <div>
            · Put Thales in a situation that would breach its license rights to the Service, including but not limited
            to: (i) work around any technical limitations in the Service that only allows you to use it in certain ways;
            (ii) reverse engineer, decompile or disassemble the Service or the underlying LLM; (iii) remove, minimize,
            block, or modify any notices or its suppliers in the Service; (iv) use the Service in any way that creates
            or propagates malware; (v) make available PRISM to any person who is not an authorized User or; (vi) use the
            Service or its data (including Outputs) to create, train or improve a similar competing product or service;
          </div>
          <div>
            · Impersonating an individual (living or dead) without explicit disclosure, in order to deceive. Or
            facilitating misleading claims of expertise or capability in sensitive areas -- for example in health,
            finance, or the law, in order to deceive;
          </div>
          <div>
            · Making decisions based on Outputs (as defined below) without appropriate human oversight, in particular if
            such decision may have an impact on any individual’s legal position, financial position, life opportunities,
            employment opportunities, human rights, or result in physical or psychological injury to an individual;
          </div>
          <div>
            · To detect content credentials or other provenance methods, marks, notices or signals with the purpose of
            removing or altering them or generating Outputs with the purpose of misleading others about whether the
            content was generated by artificial intelligence;
          </div>
          <div>
            · Process or generate content through the Service that may constitute disinformation, deception or
            inauthentic activity.
          </div>
          <div>
            · Utilize the Platform, including the creation of Lumis or the management of Knowledge Bases, for any of the
            following practices:
          </div>
          <div>
            o Cognitive Behavioral Manipulation: Developing systems that deploy subliminal techniques or purposeful
            manipulative/deceptive tactics to materially distort a person’s behavior in a manner that causes or is
            likely to cause significant harm.
          </div>
          <div>
            o Social Scoring: Evaluating or classifying individuals or groups based on their social behavior or
            known/predicted personal characteristics, leading to detrimental or unfavorable treatment in social
            contexts.
          </div>
          <div>
            o Biometric Identification: Implementing real-time or post-remote biometric identification systems in
            publicly accessible spaces, or using biometric categorization systems to infer sensitive attributes (e.g.,
            race, political opinions, trade union membership, religious beliefs).
          </div>
          <div>
            o Emotion Recognition in the Workplace: Creating agents designed to detect or infer the emotional state of
            persons within the workplace or educational institutions, unless for strictly medical or safety reasons
            previously authorized by the Legal Department.
          </div>
          <div>
            o Predictive Policing: Assessing the risk of an individual committing a criminal offense based solely on
            profiling or personality traits.
          </div>
          <div>
            o Indiscriminate Scraping: Creating or expanding facial recognition databases through the untargeted
            scraping of facial images from the internet or CCTV footage.
          </div>
          <h3>2. When using the Service, Users shall take all reasonable steps to prevent</h3>
          <div>
            · Ingesting or using, any personal data in the prompts or Input or infer personal data (i.e., use prompts to
            deduce) any personal data, even if these personal data are already publicly available or if they are
            pseudonymized without having obtained specific authorization from LC&C Department and the DPO team. When
            applicable, Users shall handle personal data in accordance with Thales privacy and data protection
            requirements, assessments, and processes; and
          </div>
          <div>
            · Facilitating the infringement of intellectual property rights. Users shall not ask to reproduce, imitate
            or use as inspiration protected content, in order to generate Outputs.
          </div>
          <h3>
            3. User acknowledge that PRISM may not be suitable for scenarios where up-to-date, factually accurate
            information is crucial. See section "Output" above
          </h3>
        </div>
        <div className={styles.gcuSection}>
          <h2>Misuse Report</h2>
          <div>
            Users acknowledge that PRISM includes a content management system that works alongside the LLMs to filter
            potentially harmful content. Users shall not attempt to override, deactivate or abuse the said content
            management system. Users shall promptly report to Thales any suspicion that the Service is being used in a
            manner that is abusive or illegal, infringes Thales’, Users’ or a third party’ rights, or violates these
            Terms of Use. Users shall similarly immediately report any PRISM adversarial Outputs (i.e., any Output that
            has been generated otherwise than expected given the prompt/input or in a way that is unexpectedly abusive
            or illegal, that may be seen as a discriminatory bias, or infringes Thales’, Users’ or a third party’
            rights, that could be an hallucination…).
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Changes to Terms & Conditions</h2>
          <div>
            Thales reserves the right to modify these Terms of Use at any time, to account for changes in technology,
            legal and regulatory requirements, as well as industry best practices. Users are required to renew their
            acceptance of the updated version of the Terms of Use after any modification in order for them to continue
            to have access to PRISM. Termination Thales reserves the right to discontinue the Service at any time and
            without prior notice. Thales may also limit or suspend, without prior notice, User’s access to, or use of
            PRISM or the related Output if Thales has a reasonable basis to believe that the User’s use of the Service
            is inconsistent with requirements herein or referred to herein.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>Warranty / Limitation of Liability</h2>
          <div>
            The Service is provided "as is," without any warranty of any kind made by Thales in connection to the
            Service. Thales does not warrant in any way that the Service will be free from errors, interruptions, or
            defects. In no event shall Thales be liable for any direct, damages whatsoever including those resulting
            from loss of use, data, arising out of or in connection with the use or performance of the Service.
          </div>
        </div>
        <div className={styles.gcuSection}>
          <h2>User’s Liability</h2>
          <div>
            In the event of failure by the User to comply with these Terms of Use, User may be exposed to disciplinary
            actions.
          </div>
          <div ref={bottomRef}>
            By using the Service, you acknowledge that you have read, understood, and accepted these Terms of Use.
          </div>
        </div>
      </div>
      <div className={styles.gcuActions}>
        {gcuVersion && userDetails && userDetails.cguValidated.toString() == gcuVersion ? (
          <Link to={"/"}>
            <Button color={"primary"} variant={"filled"} size={"medium"}>
              {t("rework.gcu.backToApp")}
            </Button>
          </Link>
        ) : (
          <>
            <span className={styles.gcuLockInformation}>{t("rework.gcu.lockInformation")}</span>
            <Button
              color={"primary"}
              variant={"filled"}
              size={"medium"}
              disabled={!hasReachedBottom || isLoading}
              onClick={handleAcceptGcu}
            >
              {t("rework.gcu.validate")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
