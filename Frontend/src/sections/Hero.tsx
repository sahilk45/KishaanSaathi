
import AssistantSection from './AssistantSection'
import CtaSection from './CtaSection'
import DashboardSection from './DashboardSection'
import EnterpriseSection from './EnterpriseSection'
import FooterSection from './FooterSection'
import HeroBannerSection from './HeroBannerSection'
import IntelligenceSection from './IntelligenceSection'
import LogosSection from './LogosSection'
import MarqueeSection from './MarqueeSection'
import NavbarSection from './NavbarSection'
import StoriesSection from './StoriesSection'

const Hero = () => {
  return (
    <>
      <NavbarSection />
      <HeroBannerSection />
      <DashboardSection />
      <LogosSection />
      <IntelligenceSection />
      <AssistantSection />
      <EnterpriseSection />
      <MarqueeSection />
      <StoriesSection />
      <CtaSection />
      <FooterSection />
    </>
  )
}

export default Hero
